# Copyright (c) 2014, Freja Nordsiek
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#   Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
#   Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or  other materials provided with the
#   distribution.
#
#   Neither the name of the {organization} nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

""" Module for reading/writing Acquisition HDF5 files.

Version 0.1

"""

__version__ = "0.1"


import platform
from distutils.version import LooseVersion

import numpy as np
import h5py

import hdf5storage


def _get_supported_version(version):
    # Find the supported version it matches and return the type string
    # of the one it matches. Otherwise return None.
    loose_version = LooseVersion(version)
    # First, we need a LooseVersion lists of all versions that one might
    # see out there that are currently supported. Then, everything
    # between 0.0.1 and 1.0.0 is the same as 1.0.0.
    versions_supported = ['0.0.1', '1.0.0', '1.1.0']
    lvs = [LooseVersion(v) for v in versions_supported]

    if LooseVersion('0.0.1') <= loose_version \
            and LooseVersion('1.0.0') >= loose_version:
        return '1.0.0'

    index = lvs.index(loose_version)
    if index != -1:
        return versions_supported[index]
    else:
        return None


class Writer(object):
    def __init__(self, filename,
                 version=b'1.1.0',
                 VendorDriverDescription=b'',
                 DeviceName=b'',
                 ID=b'',
                 TriggerType=b'',
                 SampleFrequency=np.float64(-1),
                 InputType=b'',
                 NumberChannels=np.int64(-1),
                 Bits=np.int64(-1),
                 ChannelMappings=None,
                 ChannelNames=None,
                 ChannelInputRanges=None,
                 Offsets=None,
                 Scalings=None,
                 Units=None,
                 data_type=b'double',
                 data_storage_type=b'single',
                 compression='gzip',
                 compression_opts=9,
                 shuffle=True,
                 fletcher32=True,
                 chunks=(1024, None)):
        # Set this first before anything else so that nothing goes wrong
        # on deletion.
        self._file = None
        
        # Validate inputs.

        # All the simple arguments must be the right type.
        if type(version) != bytes \
                or type(VendorDriverDescription) != bytes \
                or type(DeviceName) != bytes \
                or type(ID) != bytes \
                or type(TriggerType) != bytes \
                or type(SampleFrequency) != np.float64 \
                or type(InputType) != bytes \
                or type(NumberChannels) != np.int64 \
                or type(Bits) != np.int64 \
                or type(data_type) != bytes \
                or type(data_storage_type) != bytes:
            raise ValueError('At least one input argument is not of '
                             + 'right type.')

        # Check that we have a positive number of channels.
        if NumberChannels < 1:
            raise ValueError('There must be at least one channel.')

        # If the channel mappings aren't given, make it the default
        # (incrementing integers from 0). If it is given, check it.
        if ChannelMappings is None:
            ChannelMappings = np.int64(np.r_[0:NumberChannels])
        elif type(ChannelMappings) != np.ndarray \
                or ChannelMappings.dtype.name != 'int64' \
                or ChannelMappings.shape != (NumberChannels, ):
            raise ValueError('ChannelMappings isn''t a numpy.int64 '
                             + 'row array with an element for each '
                             + 'channel.')

        # If the channel names aren't given, make it the default (all
        # b''). If it is given, check it.
        if ChannelNames is None:
            ChannelNames = np.zeros(shape=(NumberChannels, ),
                                     dtype='bytes')
        elif type(ChannelNames) != np.ndarray \
                or not ChannelNames.dtype.name.startswith('bytes') \
                or ChannelNames.shape != (NumberChannels, ):
            raise ValueError('ChannelNames isn''t a numpy.bytes_ '
                             + 'row array with an element for each '
                             + 'channel.')

        # If the channel input ranges aren't given, make it the default
        # (array from zeros). If it is given, check it.
        if ChannelInputRanges is None:
            ChannelInputRanges = np.zeros(shape=(NumberChannels, 2),
                                            dtype='float64')
        elif type(ChannelInputRanges) != np.ndarray \
                or ChannelInputRanges.dtype.name != 'float64' \
                or ChannelInputRanges.shape != (NumberChannels, 2):
            raise ValueError('ChannelInputRanges isn''t a numpy '
                             + 'float64 array with 2 columns and a ' \
                             + 'row for each channel.')

        # If the Offsets aren't given, make it the default (row of
        # zeros). If it is given, check it.
        if Offsets is None:
            Offsets = np.zeros(shape=(NumberChannels,),
                               dtype='float64')
        elif type(Offsets) != np.ndarray \
                or Offsets.dtype.name != 'float64' \
                or Offsets.shape != (NumberChannels, ):
            raise ValueError('Offsets isn''t a numpy.float64 '
                             + 'row array with an element for each '
                             + 'channel.')

        # If the Scalings aren't given, make it the default (row of
        # ones). If it is given, check it.
        if Scalings is None:
            Scalings = np.ones(shape=(NumberChannels,),
                               dtype='float64')
        elif type(Scalings) != np.ndarray \
                or Scalings.dtype.name != 'float64' \
                or Scalings.shape != (NumberChannels, ):
            raise ValueError('Scalings isn''t a numpy.float64 '
                             + 'row array with an element for each '
                             + 'channel.')

        # If the Units aren't given, make it the default (all b''). If
        # it is given, check it.
        if Units is None:
            Units = np.zeros(shape=(NumberChannels, ),
                             dtype='bytes')
        elif type(Units) != np.ndarray \
                or not Units.dtype.name.startswith('bytes') \
                or Units.shape != (NumberChannels, ):
            raise ValueError('Units isn''t a numpy.bytes_ '
                             + 'row array with an element for each '
                             + 'channel.')

        # Make a lookup of numpy types by data type value.
        self._data_types = {b'uint8': np.uint8,
                            b'uint16': np.uint16,
                            b'uint32': np.uint32,
                            b'uint64': np.uint64,
                            b'int8': np.int8,
                            b'int16': np.int16,
                            b'int32': np.int32,
                            b'int64': np.int64,
                            b'single': np.float32,
                            b'double': np.float64}

        # data_type and data_storage_types must be in the lookup.
        if data_type not in self._data_types:
            raise ValueError('data_type must be one of (' \
                + b', '.join(list(self._data_types.keys())).decode() \
                + b').')
        # data_type and data_storage_types must be in the lookup.
        if data_storage_type not in self._data_types:
            raise ValueError('data_storage_type must be one of (' \
                + b', '.join(list(self._data_types.keys())).decode() \
                + b').')

        # Check that the version is valid, and get the version string we
        # will be using.
        new_version = _get_supported_version(version.decode()).encode()
        if new_version is None:
            raise ValueError('Unsupported version.')

        # Validate chunks to make sure it is None, True, a tuple of two
        # ints, or a tuple of an int and None. All integers must be
        # positive.

        if chunks is None:
            chunks = (1024, int(NumberChannels))
        elif chunks is True:
            pass
        elif not isinstance(chunks, tuple) or len(chunks) != 2:
            raise ValueError('chunks must be None, True, or a tuple '
                             + 'an integer as the first element and '
                             + 'either an integer or None in the '
                             + 'second.')
        elif not isinstance(chunks[0], int) or chunks[0] < 1:
            raise ValueError('chunks must be None, True, or a tuple '
                             + 'an integer as the first element and '
                             + 'either an integer or None in the '
                             + 'second.')
        elif chunks[1] is None:
            chunks = (chunks[0], int(NumberChannels))
        elif not isinstance(chunks[1], int) or chunks[1] < 1:
            raise ValueError('chunks must be None, True, or a tuple '
                             + 'an integer as the first element and '
                             + 'either an integer or None in the '
                             + 'second.')

        # All inputs are validated.

        # Pack all of the information together, including putting in
        # placeholders for the start time and the number of samples
        # taken. The file type and software information is also put
        # in. All strings are converted to numpy bytes.

        software = __name__ + ' ' + __version__ + ' on ' \
            + platform.python_implementation() + ' ' \
            + platform.python_version()

        self._file_data = { \
            'Type': np.bytes_(b'Acquisition HDF5'), \
            'Version': np.bytes_(new_version), \
            'Software': np.bytes_(software), \
            'Info': { \
            'VendorDriverDescription': \
            np.bytes_(VendorDriverDescription), \
            'DeviceName': np.bytes_(DeviceName), \
            'ID': np.bytes_(ID), \
            'TriggerType': np.bytes_(TriggerType), \
            'StartTime': np.zeros(shape=(6,), dtype='float64'), \
            'SampleFrequency': SampleFrequency, \
            'InputType': np.bytes_(InputType), \
            'NumberChannels': NumberChannels, \
            'Bits': Bits, \
            'NumberSamples': np.int64(0), \
            'ChannelMappings': ChannelMappings, \
            'ChannelNames': ChannelNames, \
            'ChannelInputRanges': ChannelInputRanges, \
            'Offsets': Offsets, \
            'Scalings': Scalings, \
            'Units': Units}, \
            'Data': { \
            'Type': np.bytes_(data_type), \
            'StorageType': np.bytes_(data_storage_type)}}

        # Write it all to file, truncating it if it exists. Type
        # information should not be stored, and matlab compatibility
        # should not be done. While the former would make it easier to
        # read the strings back in the same format
        hdf5storage.write(self._file_data, path='/', filename=filename,
                          truncate_existing=True,
                          store_type_information=False,
                          matlab_compatible=False)

        # Create a growable empty DataSet for the data with all the
        # storage options set, and then keep the file handle around for
        # later. If an exception occurs, the file needs to be closed if
        # it was opened and the exception re-raised so that the caller
        # knows about it. Nothing other than that needs to be done.

        try:
            self._file = h5py.File(filename)

            self._file['/Data'].create_dataset('Data', \
                shape=(0, NumberChannels), \
                dtype=self._data_types[data_storage_type], \
                maxshape=(None, NumberChannels), \
                compression=compression, \
                compression_opts=compression_opts, \
                shuffle=shuffle, \
                fletcher32=fletcher32, \
                chunks=chunks)

            self._file.flush()
        except:
            if self._file is not None:
                self._file.close()
            raise

    def __del__(self):
        self.flush()
        if isinstance(self._file, h5py.File):
            self._file.flush()
            self._file.close()

    def flush(self):
        # Doesn't do anything right now because everything is just
        # written without concern for chunking, but it needs to be here
        # for later when the writing is done better.
        pass

    def add_data(self, data, flush_buffer=True):
        # Check to see if data matches the right data format and shape.
        if not isinstance(data, np.ndarray) or len(data.shape) != 2 \
                or data.shape[1] \
                != self._file_data['Info']['NumberChannels']:
            raise ValueError('data is not the right type, shape, or '
                             + 'format.')

        # Resize the Dataset to fit data and then append it onto the
        # end. If the dtypes don't match, it is converted (storage type
        # and acquired type need not be the same).
        dset = self._file['/Data/Data']
        old_shape = dset.shape
        dset.resize((old_shape[0] + data.shape[0], old_shape[1]))
        if data.dtype.name == dset.dtype.name:
            dset[old_shape[0]:dset.shape[0], :] = data
        else:
            dset[old_shape[0]:dset.shape[0], :] = dset.dtype.type(data)

        # Set NumberSamples to the new value.
        self._file['/Info/NumberSamples'][()] = np.int64(dset.shape[0])

        # Flush the changes to disk so nothing is lost if we hang.
        self._file.flush()

    @property
    def number_samples(self):
        return self._file['/Info/NumberSamples'][()]

    @property
    def StartTime(self):
        return self._file['/Info/StartTime'][...]

    @StartTime.setter
    def StartTime(self, value):
        if type(value) == np.ndarray and value.dtype.name == 'float64' \
                and value.shape == (6, ):
            self._file['/Info/StartTime'][:] = value
