# Copyright (c) 2015 Allen Institute, California Institute of Technology, 
# New York University School of Medicine, the Howard Hughes Medical 
# Institute, University of California, Berkeley, GE, the Kavli Foundation 
# and the International Neuroinformatics Coordinating Facility. 
# All rights reserved.
#     
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following 
# conditions are met:
#     
# 1.  Redistributions of source code must retain the above copyright 
#     notice, this list of conditions and the following disclaimer.
#     
# 2.  Redistributions in binary form must reproduce the above copyright 
#     notice, this list of conditions and the following disclaimer in 
#     the documentation and/or other materials provided with the distribution.
#     
# 3.  Neither the name of the copyright holder nor the names of its 
#     contributors may be used to endorse or promote products derived 
#     from this software without specific prior written permission.
#     
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT 
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS 
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE 
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, 
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; 
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER 
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT 
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN 
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE 
# POSSIBILITY OF SUCH DAMAGE.
import sys
import os.path
import shutil
import time
import json
import traceback
import h5py
import copy
import numpy as np
import types
from datetime import datetime


from .base import TimeSeries, Module
from .epoch import Epoch
from .ecephys import ElectrodeGroup, ElectricalSeries
from .core import docval, getargs, NWBContainer

# VERS_MAJOR = 1
# VERS_MINOR = 0
# VERS_PATCH = 5
# 
# __version__ = "%d.%d.%d" % (VERS_MAJOR, VERS_MINOR, VERS_PATCH)
# FILE_VERSION_STR = "NWB-%s" % __version__
# 
# def get_major_vers():
#     return VERS_MAJOR
# 
# def get_minor_vers():
#     return VERS_MINOR
# 
# def get_patch_vers():
#     return VERS_PATCH
# 
# def get_file_vers_string():
#     return FILE_VERSION_STR
# 
# def create_identifier(base_string):
#     """ Creates an identifying string for the file, hopefully unique 
#         in and between labs, based on the supplied base string, the NWB file
#         version, and the time the file was created. The base string
#         should contain the name of the lab, experimenter and project, or
#         some other string that is unique to a given lab
#     """
#     return base_string + "; " + FILE_VERSION_STR + "; " + time.ctime()
# 
# 
# # it is too easy to create an object and forget to finalize it
# # keep track of when each object is created and finalized, and
# #   provide a way to detect when finalization doesnt occur
# serial_number = 0
# object_register = {}
# def register_creation(name):
#     global serial_number, object_register
#     num = serial_number
#     object_register[str(num)] = name
#     serial_number += 1
#     return num


class NWBFile(NWBContainer):
    """
    A representation of an NWB file.
    """
    __nwbfields__ = ('experimenter',
                     'description',
                     'experiment_description',
                     'session_id',
                     'lab',
                     'institution',
                     'raw_data'
                     'stimulus'
                     'stimulus_template'
                     'ec_electrodes'
                     'ic_electrodes')

    __nwb_version = '1.0.4'

    @docval({'name': 'file_name', 'type': str, 'doc': 'path to NWB file'},
            {'name': 'description', 'type': str, 'doc': 'a description of the session where this data was generated'},
            {'name': 'experimenter', 'type': str, 'doc': 'name of person who performed experiment', 'default': None},
            {'name': 'experiment_description', 'type': str, 'doc': 'general description of the experiment', 'default': None},
            {'name': 'session_id', 'type': str, 'doc': 'lab-specific ID for the session', 'default': None},
            {'name': 'institution', 'type': str, 'doc': 'institution(s) where experiment is performed', 'default': None},
            {'name': 'lab', 'type': str, 'doc': 'lab where experiment was performed', 'default': None})
    def __init__(self, **kwargs):
        super(NWBFile, self).__init__()
        self.__filename = getargs('file_name', kwargs)
        self.__start_time = datetime.utcnow()
        self.__file_id = '%s %s' % (self.__filename, self.__start_time.strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.__description = getargs('description', kwargs)

        self.__raw_data = dict()
        self.__stimulus = dict()
        self.__stimulus_template = dict()

        self.modules = dict()
        self.epochs = dict()
        self.__ec_electrodes = dict()
        self.__ec_electrode_idx = dict()

        recommended = [
            'experimenter',
            'experiment_description',
            'session_id',
            'lab',
            'institution'
        ]
        for attr in recommended:
            setattr(self, attr, kwargs.get(attr, None))

    @property
    def nwb_version(self):
        return self.__nwb_version

    @property
    def start_time(self):
        return self.__start_time

    @property
    def filename(self):
        return self.__filename

    @property
    def session_description(self):
        return self.__description

    @property
    def file_id(self):
        return self.__file_id

    @property
    def raw_data(self):
        return tuple(self.__raw_data.values())

    @property
    def stimulus(self):
        return tuple(self.__stimulus.values())

    @property
    def stimulus_template(self):
        return tuple(self.__stimulus_template.values())

    @property
    def ec_electrodes(self):
        return tuple(self.__ec_electrodes.values())

    def is_raw_data(self, ts):
        return self.__exists(ts, self.__raw_data)

    def is_stimulus(self, ts):
        return self.__exists(ts, self.__stimulus)

    def is_stimulus_template(self, ts):
        return self.__exists(ts, self.__stimulus_template)

    def __exists(self, ts, d):
        return ts.name in d

    @docval({'name': 'name', 'type': str, 'doc': 'the name of the epoch, as it will appear in the file'},
            {'name': 'start', 'type': float, 'doc': 'the starting time of the epoch'},
            {'name': 'stop', 'type': float, 'doc': 'the ending time of the epoch'},
            {'name': 'tags', 'type': (tuple, list), 'doc': 'tags for this epoch', 'default': list()},
            {'name': 'description', 'type': str, 'doc': 'a description of this epoch', 'default': None})
    def create_epoch(self, **kwargs):
        """
        Creates a new Epoch object. Epochs are used to track intervals
        in an experiment, such as exposure to a certain type of stimuli
        (an interval where orientation gratings are shown, or of 
        sparse noise) or a different paradigm (a rat exploring an 
        enclosure versus sleeping between explorations)
        """
        name, start, stop, tags, description = getargs('name', 'start', 'stop', 'tags', 'description', kwargs)
        epoch = Epoch(name, start, stop, description=description, tags=tags, parent=self)
        self.epochs[name] = epoch
        return epoch

    def get_epoch(self, name):
        return self.__get_epoch(name)

    @docval({'name': 'epoch', 'type': (str, Epoch, list, tuple), 'doc': 'the name of an epoch or an Epoch object or a list of names of epochs or Epoch objects'},
            {'name': 'timeseries', 'type': (str, TimeSeries, list, tuple), 'doc': 'the name of a timeseries or a TimeSeries object or a list of names of timeseries or TimeSeries objects'})
    def set_epoch_timeseries(self, **kwargs):
        """
        Add one or more TimSeries datasets to one or more Epochs
        """
        epoch, timeseries = getargs('epoch', 'timeseries', kwargs)
        if isinstance(epoch, list):
            ep_objs = [self.__get_epoch(ep) for ep in epoch]
        else:
            ep_objs = [self.__get_epoch(epoch)]

        if isinstance(timeseries, list):
            ts_objs = [self.__get_timeseries(ts) for ts in timeseries]
        else:
            ts_objs = [self.__get_timeseries(timeseries)]

        for ep in ep_objs:
            for ts in ts_objs:
                ep.add_timeseries(ts)

    def __get_epoch(self, epoch):
        if isinstance(epoch, Epoch):
            ep = epoch
        elif isinstance(epoch, str): 
            ep = self.epochs.get(epoch)
            if not ep:
                raise KeyError("Epoch '%s' not found" % epoch)
        else:
            raise TypeError(type(epoch))
        return ep

    def __get_timeseries(self, timeseries):
        if isinstance(timeseries, TimeSeries):
            ts = timeseries 
        elif isinstance(timeseries, str): 
            ts = self.__raw_data.get(timeseries, 
                    self.__stimulus.get(timeseries, 
                        self.__stimulus_template.get(timeseries, None)))
            if not ts:
                raise KeyError("TimeSeries '%s' not found" % timeseries)
        else:
            raise TypeError(type(timeseries))
        return ts

    def link_timeseries(self, ts):
        pass

    @docval({'name': 'ts', 'type': TimeSeries, 'doc': 'the  TimeSeries object to add'},
            {'name': 'epoch', 'type': (str, Epoch, list, tuple), 'doc': 'the name of an epoch or an Epoch object or a list of names of epochs or Epoch objects', 'default': None},
            returns="the TimeSeries object")
    def add_raw_timeseries(self, **kwargs):
        ts, epoch = getargs('ts', 'epoch', kwargs)
        self.__set_timeseries(self.__raw_data, ts, epoch)

    @docval({'name': 'ts', 'type': TimeSeries, 'doc': 'the  TimeSeries object to add'},
            {'name': 'epoch', 'type': (str, Epoch), 'doc': 'the name of an epoch or an Epoch object or a list of names of epochs or Epoch objects', 'default': None},
            returns="the TimeSeries object")
    def add_stimulus(self, **kwargs):
        ts, epoch = getargs('ts', 'epoch', kwargs)
        self.__set_timeseries(self.__stimulus, ts, epoch)

    @docval({'name': 'ts', 'type': TimeSeries, 'doc': 'the  TimeSeries object to add'},
            {'name': 'epoch', 'type': (str, Epoch), 'doc': 'the name of an epoch or an Epoch object or a list of names of epochs or Epoch objects', 'default': None},
            returns="the TimeSeries object")
    def add_stimulus_template(self, **kwargs):
        ts, epoch = getargs('ts', 'epoch', kwargs)
        self.__set_timeseries(self.__stimulus_template, ts, epoch)

    def __set_timeseries(self, ts_dict, ts, epoch=None):
        ts_dict[ts.name] = ts
        ts.parent = self
        if epoch:
            self.set_epoch_timeseries(epoch, ts)
#
#  Not sure what purpose this serves yet, so keeping it around for reference: AJT 09-02-2017
#
#    def create_reference_image(self, stream, name, fmt, desc, dtype=None):
#        """ Adds documentation image (or movie) to file. This is stored
#            in /acquisition/images/.
#
#            Args:
#                *stream* (binary) Data stream of image (eg, binary contents of .png image)
#
#                *name* (text) Name that image will be stored as
#
#                *fmt* (text) Format of the image (eg, "png", "avi")
#
#                *desc* (text) Descriptive text describing the image
#
#                *dtype* (text) Optional field specifying the h5py datatype to use to store *stream*
#
#            Returns:
#                *nothing*
#        """
#        fp = self.file_pointer
#        img_grp = fp["acquisition"]["images"]
#        if name in img_grp:
#            self.fatal_error("Reference image %s alreayd exists" % name)
#        if dtype is None:
#            img = img_grp.add_dataset(name, stream)
#        else:
#            img = img_grp.add_dataset(name, stream, dtype=dtype)
#        img.set_attribute("format", np.string_(fmt))
#        img.set_attribute("description", np.string_(desc))


    @docval({'name': 'name', 'type': (str, int), 'doc': 'a unique name or ID for this electrode'},
            {'name': 'coord', 'type': (tuple, list, np.ndarray), 'doc': 'the x,y,z coordinates of this electrode'},
            {'name': 'desc', 'type': str, 'doc': 'a description for this electrode'},
            {'name': 'dev', 'type': str, 'doc': 'the device this electrode was recorded from on'},
            {'name': 'loc', 'type': str, 'doc': 'a description of the location of this electrode'},
            {'name': 'imp', 'type': (float, tuple), 'doc': 'the impedance of this electrode. A tuple can be provided to specify a range', 'default': -1.0},
            returns='the electrode group', rtype=ElectrodeGroup)
    #TODO: investigate bug with electrode_group and electrode_map
    def create_electrode_group(self, **kwargs):
        """Add an electrode group (e.g. a probe, shank, tetrode). 
        """
        name, coord, desc, dev, loc, imp = getargs('name', 'coord', 'desc', 'dev', 'loc', 'imp', kwargs)
        elec_grp = ElectrodeGroup(name, coord, desc, dev, loc, imp=imp, parent=self)
        self.set_electrode_group(elec_grp)
        return elec_grp

    @docval({'name': 'elec_grp', 'type': ElectrodeGroup, 'doc': 'the ElectrodeGroup object to add to this NWBFile'})
    def set_electrode_group(self, **kwargs):
        elec_grp = getargs('elec_grp', kwargs)
        elec_grp.parent = self
        name = elec_grp.name
        self.__ec_electrodes[name] = elec_grp
        self.__ec_electrode_idx[name] = len(self.__ec_electrode_idx)
        return self.__ec_electrode_idx[name]

    @docval({'name': 'name', 'type': (ElectrodeGroup, str), 'doc': 'the name of the electrode group or the ElectrodeGroup object'})
    def get_electrode_group_idx(self, **kwargs):
        name = getargs('name', kwargs)
        if isinstance(name, ElectrodeGroup):
            name = name.name
        return self.__ec_electrode_idx.get(name, None)

    @docval({'name': 'name', 'type': (ElectrodeGroup, str), 'doc': 'the name of the electrode group'})
    def get_electrode_group(self, name):
        return self.__ec_electrodes.get(name)

    @docval({'name': 'name',  'type': str, 'doc': 'the name of the processing module'},
            {'name': 'description',  'type': str, 'doc': 'description of the processing module'},
            returns="a processing module", rtype=Module)
    def create_processing_module(self, **kwargs):
        """ Creates a Module object of the specified name. Interfaces can
            be created by the module and will be stored inside it
        """
        name, description = get_args('name', 'description', kwargs)
        ret = Module(name, description)
        self.add_processing_module(ret)
        return ret

    @docval({'name': 'module',  'type': Module, 'doc': 'the processing module to add to this file'})
    def add_processing_module(self, **kwargs):
        module = getargs('module', kwargs)
        module.parent = self
        self.modules[module.name] = module
