#!/usr/bin/env python3

import sys
import os
import stat
import os.path
import argparse

from yaml import load, dump
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

def mkdirp(path):
    if not path:
        return
    try:
        os.makedirs(path)
    except FileExistsError:
        pass

class Nesting:
    def __init__(self):
        self.nesting = 0

    def set_nesting(self, level):
        self.nesting = level

    @property
    def nest(self):
        return self.nesting

class Command(Nesting):
    def __init__(self, cmd):
        self.cmd = cmd
        super().__init__()

    def __str__(self):
        return self.nest * 4 * ' ' + '{:s}\n'.format(self.cmd)

class BodyMember(Nesting):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        super().__init__()
    
    def __str__(self):
        return self.nest * 4 * ' ' + '{:s} = {:s}\n'.format(self.name, self.value)

class Branch(Nesting):
    def __init__(self, sline, eline='end'):
        self.sline = sline
        self.eline = eline
        self.children = []
        super().__init__()
       
    @property
    def start(self):
        return self.nest * 4 * ' ' + self.sline
    
    @property
    def end(self):
        return self.nest * 4 * ' ' + self.eline

    def add(self, children):
        self.children += children

    def append(self, child):
        self.children.append(child)

    def __str__(self):
        s = self.start + '\n'
        for child in self.children:
            child.set_nesting(self.nest + 1)
            s += child.__str__() 
        s += self.end + ('\n' if self.nest else '')
        return s

class Args:
    def __init__(self):
        self.generate_vagrant_file = None
        self.build_box = None
        self.file_name = None

    @property
    def filename(self):
        return self.file_name
    
    @property
    def machinename(self):
        return self.generate_vagrant_file

    @property
    def build(self):
        return self.build_box

class ArgsParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description = 'This utility intended to convert .yaml files \
                           into Vagrantfile with build box script'
        )
        self.parser.add_argument(
            '-g', '--generate-vagrant-file',
            type=str,
            help='generates Vagrantfiles for specified machine'
        )
        self.parser.add_argument(
            '-f', '--file-name',
            type=str,
            required=True,
            help='machine configuration file'
        )

    def Parse(self):
        a = Args()
        return self.parser.parse_args(args=sys.argv[1:], namespace=a)
        

class Configs:
    def __init__(self, filename):
        with open(filename) as f:
            data = load(f.read())
        if data.get('machine') is None:
            raise AttributeError('Wrong ' +filename+ ' format, "machine" tag is absent')
        self.machines = data['machine']

    def items(self):
        return self.machines.items()

class Machine:
    def __init__(self, name, config):
        self.name = name
        self.configure(config)

    def configure(self, config):
        if config.get('box') is None or config.get('provider') is None or \
           config.get('driver') is None:
            raise AttributeError('box name, provider or driver are abcent')

        self.box = '"' + config['box'] + '"'
        self.provider = config['provider']
        self.driver = config['driver']
      
        self.before = []
        if config.get('before') is not None:
            self.before = [Command(cmd) for cmd in config['before']] 
        
        self.after = []
        if config.get('after') is not None:
            self.after = [Command(cmd) for cmd in config['after']]
       
        self.install_cmd = []
        if config.get('software') is not None:
            for soft_name, details in config['software'].items():
                if details.get('installation') is None:
                    raise AttributeError('SHIT')
                self.install_cmd += [Command(cmd) for cmd in details['installation']]
                if details.get('cpe') is not None:
                    self.install_cmd += [Command('echo "{:s}" >> cpe.txt'.format(details['cpe']))]
                if details.get('cve') is not None:
                    self.install_cmd += [Command('echo "{:s}" >> cve.txt'.format(cve)) for cve in details['cve']]
    

    def gen_vagrantfile(self):
        branch = Branch('Vagrant.configure("2") do |config|')
        branch.append(BodyMember('config.vm.box', self.box))
        
        branch.append(Branch('config.vm.define "{:s}"'.format(self.name),''))
        
        provider_branch = Branch('config.vm.provider "'+self.provider+'" do |vb|')
        provider_branch.append(BodyMember('vb.driver', '"'+self.driver+'"')) 
        provider_branch.append(BodyMember('vb.memory', '1024')) 
        branch.append(provider_branch)
        
        script_branch = Branch('config.vm.provision "shell", inline: <<-SHELL', 'SHELL')
        script_branch.add(self.before)
        script_branch.add(self.install_cmd)
        script_branch.add(self.after) 
        branch.append(script_branch)
        
        return branch
    

def write_vagrantfile(machine):
    if machine is None or not isinstance(machine, Machine):
        raise AttributeError('There is no such machine in config file')
    vf = machine.gen_vagrantfile()

    mkdirp(machine.name)
    with open(os.path.join(machine.name, 'Vagrantfile'), 'w') as file:
        file.write(vf.__str__())


def write_build_script(machine):
    if machine is None or not isinstance(machine, Machine):
        raise AttributeError("Bad Machine instance")
   
    path = os.path.join(machine.name, 'build.sh')
    with open(path, 'w') as file:
        file.writelines([
            'vagrant up --provider={:s}\n'.format(machine.provider),
            'vagrant package --output {:s}.box'.format(machine.name)
        ]) 
    
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC)


def main():
    parser = ArgsParser()
    args = parser.Parse()
   
    configs = Configs(args.filename)
    machines = {name: Machine(name, config) for name, config in configs.items()} 

    if args.machinename is not None:
        if args.machinename == 'all':
            for machine in machines.values():
                write_vagrantfile(machine)
                write_vagrantfile(machine)
        else:
            machine = machines.get(args.machinename)
            write_vagrantfile(machine)
            write_build_script(machine)

if __name__ == '__main__':
    main()
