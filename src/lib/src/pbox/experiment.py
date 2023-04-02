# -*- coding: UTF-8 -*-
from tinyscript import logging
from tinyscript.helpers import ansi_seq_strip, confirm, Path
from tinyscript.report import *

from .common import *
from .common.rendering import render
from .common.utils import *
from .learning import *


__all__ = ["Experiment"]


COMMIT_VALID_COMMANDS = [
    # OS commands
    "cd", "cp", "mkdir", "mv",
    # packing-box commands
    "dataset", "detector", "model", "packer", "unapcker", "visualizer",
]


class Experiment:
    """ Folder structure:
    
    [name]
      +-- conf          custom YAML configuration files
      +-- datasets      datasets specific to the experiment
      +-- models        models specific to the experiment
      +-- (figures)     figures generated with visualization tools
      +-- (scripts)     additional scripts
      +-- README.md     notes for explaining the experiment
    """
    @logging.bindLogger
    def __init__(self, name="experiment", load=True, **kw):
        name = check_name(Path(name).basename)
        self.path = Path(config['experiments'].joinpath(name), create=True).absolute()
        if load:
            for folder in ["conf", "datasets", "models"]:
                folder = self.path.joinpath(folder)
                if not folder.exists():
                    folder.mkdir()
            self['README'].touch()
            config['experiment'] = config['workspace'] = self.path
            # setup YAML configurations from the experiment in the config
            for conf in self.path.joinpath("conf").listdir():
                config[conf.stem] = conf
    
    def __getitem__(self, name):
        """ Get something from the experiment folder, either a config file, a dataset or a model.
        
        NB: In the case of YAML configuration files, this method aims to return the actually used YAML, not specifically
             the one from the experiment (if exists) ; therefore, when a YAML has not been edited within the scope of
             the experiment yet, this method will return the YAML from the main workspace.
        """
        # case 1: 'name' is README(.md) or commands(.rc) ; return a Path instance
        if name in ["README", "README.md"]:
            return self.path.joinpath("README.md")
        if name in ["commands", "commands.rc"]:
            return self.path.joinpath("commands.rc")
        # case 2: 'name' matches a reserved word for a YAML configuration file ; return a Path instance
        #          get it either from the main workspace or, if existing, from the experiment
        if name in config.DEFAULTS['definitions'].keys():
            conf = self.path.joinpath("conf").joinpath(name + ".conf")
            if not conf.exists():
                conf = config[name]
            return conf
        # case 3: 'name' matches a dataset from the experiment ; return a (Fileless)Dataset instance
        for ds in self.path.joinpath("datasets").listdir():
            if name == ds.stem:
                return open_dataset(ds)
        # case 4: 'name' matches a model from the experiment ; return a (Dumped)Model instance
        for ds in self.path.joinpath("models").listdir():
            if name == ds.stem:
                return open_model(ds)
        raise KeyError(name)
    
    def close(self, **kw):
        """ Close the currently open experiment. """
        del config['experiment']
    
    def commit(self, force=False, **kw):
        """ Commit the latest executed OS command to the resource file (.rc). """
        l = self.logger
        rc = self['commands']
        rc.touch()
        for rc_last_line in rc.read_lines():
            pass
        try:
            rc_last_line
        except NameError:
            rc_last_line = ""
        hist = list(Path("~/.bash_history", expand=True).read_lines())
        while len(hist) > 0 and all(not hist[-1].startswith(cmd + " ") for cmd in COMMIT_VALID_COMMANDS):
            hist.pop()
        if len(hist) == 0 or hist[-1].strip() == rc_last_line.strip():
            l.warning("Nothing to commit")
        elif force or confirm("Do you really want to commit this command: %s ?" % hist[-1]):
            l.debug("writing command '%s' to commands.rc..." % hist[-1])
            with rc.open('a') as f:
                f.write(hist[-1].strip())
    
    def compress(self, **kw):
        """ Compress the experiment by converting all datasets to fileless datasets. """
        l, done = self.logger, False
        for dset in Path(config['datasets']).listdir(Dataset.check):
            l.info("Dataset: %s" % dset)
            open_dataset(dset).convert()
            done = True
        if not done:
            l.warning("No dataset to be converted")
    
    def edit(self, **kw):
        """ Edit the README or a YAML configuration file. """
        l, conf = self.logger, kw.get('config')
        p = self[conf] # can be README.md, commands.rc or YAML config files
        try:
            p_main, p_exp = config[conf], self.path.joinpath("conf").joinpath(conf + ".conf")
            if not p_main.is_samepath(p_exp):
                l.debug("copying configuration file from '%s'..." % p_main)
                p_main.copy(p_exp)
            l.debug("editing experiment's %s configuration..." % conf)
            edit_file(p_exp, text=True, logger=l)
        except KeyError:
            l.debug("editing experiment's %s..." % p.basename)
            edit_file(p, text=True, logger=l)
    
    def list(self, raw=False):
        """ List all valid experiment folders. """
        data, headers = [], ["Name", "#Datasets", "#Models", "Custom configs"]
        for folder in config['experiments'].listdir(Experiment.check):
            exp = Experiment(folder, False)
            cfg = [f.stem for f in exp.path.joinpath("conf").listdir(Path.is_file) if f.extension == ".conf"]
            data.append([folder.basename, Dataset.count(), Model.count(), ", ".join(cfg)])
        if len(data) > 0:
            render(*[Section("Experiments (%d)" % len(data)), Table(data, column_headers=headers)])
        else:
            self.logger.warning("No experiment found in the workspace (%s)" % config['experiments'])
    
    def show(self, **kw):
        """ Show an overview of the experiment. """
        Dataset(load=False).list()
        Model(load=False).list()
    
    @property
    def name(self):
        """ Dummy shortcut for dataset's path.basename. """
        return self.path.basename
    
    @staticmethod
    def check(folder):
        try:
            Experiment.validate(folder)
            return True
        except (TypeError, ValueError):
            return False
    
    @staticmethod
    def validate(folder, warn=False, logger=None):
        f = config['experiments'].joinpath(folder)
        if not f.exists():
            raise ValueError("Does not exist")
        if not f.is_dir():
            raise ValueError("Not a folder")
        for fn in ["conf", "datasets", "models"]:
            if not f.joinpath(fn).exists():
                raise ValueError("Does not have %s" % fn)
        for cfg in f.joinpath("conf").listdir():
            if cfg.stem not in config.DEFAULTS['definitions'].keys() or cfg.extension != ".conf":
                raise ValueError("Unknown configuration file '%s'" % cfg)
        for fn in f.listdir(Path.is_dir):
            if fn not in ["conf", "datasets", "models", "scripts"] and warn and logger is not None:
                logger.warning("Unknown subfolder '%s'" % fn)
        for fn in f.listdir(Path.is_file):
            if fn not in ["commands.rc", "README.md"] and warn and logger is not None:
                logger.warning("Unknown file '%s'" % fn)
        return f
