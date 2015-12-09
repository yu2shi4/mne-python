# Author: Mainak Jas <mainak.jas@telecom-paristech.fr>
#
# License: BSD (3-clause)

import os.path as op
import numpy as np
import warnings

from ...utils import logger, verbose
from ..meas_info import _empty_info
from ..base import _BaseRaw, _mult_cal_one, _check_update_montage
from ..constants import FIFF
from ...channels.montage import Montage
from ...epochs import _BaseEpochs
from ...event import read_events
from ...externals.six import string_types


def _get_info(eeg, montage, eog=None):
    """Get measurement info.
    """
    info = _empty_info(sfreq=eeg.srate)
    info['nchan'] = eeg.nbchan

    # add the ch_names and info['chs'][idx]['loc']
    path = None
    if len(eeg.chanlocs) > 0:
        ch_names, pos = [], []
        kind = 'user_defined'
        selection = np.arange(len(eeg.chanlocs))
        for chanloc in eeg.chanlocs:
            ch_names.append(chanloc.labels)
            pos.append([chanloc.X, chanloc.Y, chanloc.Z])
        montage = Montage(np.array(pos), ch_names, kind, selection)
    elif isinstance(montage, string_types):
        path = op.dirname(montage)
    _check_update_montage(info, montage, path=path,
                          update_ch_names=True)

    # update the info dict
    cal = 1e-6
    if eog is None:
        eog = []
    for ch in info['chs']:
        ch['cal'] = cal
        if ch['ch_name'].startswith('EOG') or ch['ch_name'] in eog:
            ch['coil_type'] = FIFF.FIFFV_COIL_NONE
            ch['kind'] = FIFF.FIFFV_EOG_CH

    return info


def read_raw_eeglab(input_fname, montage=None, eog=None, preload=False,
                    verbose=None):
    """Read an EEGLAB .set file

    Parameters
    ----------
    input_fname : str
        Path to the .set file.
    montage : str | None | instance of montage
        Path or instance of montage containing electrode positions.
        If None, sensor locations are (0,0,0). See the documentation of
        :func:`mne.channels.read_montage` for more information.
    eog : list or tuple
        Names of channels or list of indices that should be designated
        EOG channels. If None (default), the channel names beginning with
        ``EOG`` are used.
    preload : bool or str (default False)
        Preload data into memory for data manipulation and faster indexing.
        If True, the data will be preloaded into memory (fast, requires
        large amount of memory). If preload is a string, preload is the
        file name of a memory-mapped file which is used to store the data
        on the hard drive (slower, requires less memory). Note that
        preload=False will be effective only if the data is stored in a
        separate binary file.
    verbose : bool, str, int, or None
        If not None, override default verbose level (see mne.verbose).

    Returns
    -------
    raw : Instance of RawSet
        A Raw object containing EEGLAB .set data.

    Notes
    -----
    .. versionadded:: 0.11.0

    See Also
    --------
    mne.io.Raw : Documentation of attribute and methods.
    """
    return RawSet(input_fname=input_fname, montage=montage, eog=eog,
                  preload=preload, verbose=verbose)


def read_epochs_eeglab(input_fname, events=None, event_id=None, montage=None,
                       verbose=None):
    """Reader function for KIT epochs files

    Parameters
    ----------
    input_fname : str
        Path to the .set file.
    events : str | array, shape (n_events, 3) | None
        Path to events file. If array, it is the events typically returned
        by the read_events function. If some events don't match the events
        of interest as specified by event_id,they will be marked as 'IGNORED'
        in the drop log. If None, it is constructed from the EEGLAB (.set) file
        with each unique event encoded with a different integer.
    event_id : int | list of int | dict | None
        The id of the event to consider. If dict,
        the keys can later be used to acces associated events. Example:
        dict(auditory=1, visual=3). If int, a dict will be created with
        the id as string. If a list, all events with the IDs specified
        in the list are used. If None, the event_id is constructed from the
        EEGLAB (.set) file with each descriptions copied from `eventtype`.
    montage : str | None | instance of montage
        Path or instance of montage containing electrode positions.
        If None, sensor locations are (0,0,0). See the documentation of
        :func:`mne.channels.read_montage` for more information.
    verbose : bool, str, int, or None
        If not None, override default verbose level (see mne.verbose).

    Returns
    -------
    epochs : instance of Epochs
        The epochs.

    Notes
    -----
    .. versionadded:: 0.11.0


    See Also
    --------
    mne.Epochs : Documentation of attribute and methods.
    """
    epochs = EpochsSet(input_fname=input_fname, events=events,
                       event_id=event_id, montage=montage, verbose=verbose)
    return epochs


class RawSet(_BaseRaw):
    """Raw object from EEGLAB .set file.

    Parameters
    ----------
    input_fname : str
        Path to the .set file.
    montage : str | None | instance of montage
        Path or instance of montage containing electrode positions.
        If None, sensor locations are (0,0,0). See the documentation of
        :func:`mne.channels.read_montage` for more information.
    eog : list or tuple
        Names of channels or list of indices that should be designated
        EOG channels. If None (default), the channel names beginning with
        ``EOG`` are used.
    preload : bool or str (default False)
        Preload data into memory for data manipulation and faster indexing.
        If True, the data will be preloaded into memory (fast, requires
        large amount of memory). If preload is a string, preload is the
        file name of a memory-mapped file which is used to store the data
        on the hard drive (slower, requires less memory).
    verbose : bool, str, int, or None
        If not None, override default verbose level (see mne.verbose).

    Returns
    -------
    raw : Instance of RawSet
        A Raw object containing EEGLAB .set data.

    Notes
    -----
    .. versionadded:: 0.11.0

    See Also
    --------
    mne.io.Raw : Documentation of attribute and methods.
    """
    @verbose
    def __init__(self, input_fname, montage, eog=None, preload=False,
                 verbose=None):
        """Read EEGLAB .set file.
        """
        from scipy import io
        basedir = op.dirname(input_fname)
        eeg = io.loadmat(input_fname, struct_as_record=False,
                         squeeze_me=True)['EEG']

        if not isinstance(eeg.data, string_types) and not preload:
            warnings.warn('Data will be preloaded. preload=False is not '
                          'supported when the data is stored in the .set file')
        if eeg.trials != 1:
            raise TypeError('The number of trials is %d. It must be 1 for raw'
                            ' files' % eeg.trials)

        last_samps = [eeg.pnts - 1]
        info = _get_info(eeg, montage, eog)

        # read the data
        if isinstance(eeg.data, string_types):
            data_fname = op.join(basedir, eeg.data)
            logger.info('Reading %s' % data_fname)

            super(RawSet, self).__init__(
                info, preload, filenames=[data_fname], last_samps=last_samps,
                orig_format='double', verbose=verbose)
        else:
            data = eeg.data.reshape(eeg.nbchan, -1, order='F')
            data = data.astype(np.double)
            super(RawSet, self).__init__(
                info, data, filenames=[input_fname], last_samps=last_samps,
                orig_format='double', verbose=verbose)

    def _read_segment_file(self, data, idx, fi, start, stop, cals, mult):
        """Read a chunk of raw data"""
        n_bytes = 4
        nchan = self.info['nchan']
        data_offset = self.info['nchan'] * start * n_bytes
        data_left = (stop - start) * nchan
        # Read up to 100 MB of data at a time.
        n_blocks = 100000000 // n_bytes
        blk_size = min(data_left, (n_blocks // nchan) * nchan)

        with open(self._filenames[fi], 'rb', buffering=0) as fid:
            fid.seek(data_offset)
            # extract data in chunks
            for blk_start in np.arange(0, data_left, blk_size) // nchan:
                blk_size = min(blk_size, data_left - blk_start * nchan)
                block = np.fromfile(fid,
                                    dtype=np.float32, count=blk_size)
                block = block.reshape(nchan, -1, order='F')
                blk_stop = blk_start + block.shape[1]
                data_view = data[:, blk_start:blk_stop]
                _mult_cal_one(data_view, block, idx, cals, mult)
        return data


class EpochsSet(_BaseEpochs):
    """Epochs from EEGLAB .set file

    Parameters
    ----------
    input_fname : str
        Path to the .set file.
    events : str | array, shape (n_events, 3) | None
        Path to events file. If array, it is the events typically returned
        by the read_events function. If some events don't match the events
        of interest as specified by event_id,they will be marked as 'IGNORED'
        in the drop log. If None, it is constructed from the EEGLAB (.set) file
        with each unique event encoded with a different integer.
    event_id : int | list of int | dict | None
        The id of the event to consider. If dict,
        the keys can later be used to acces associated events. Example:
        dict(auditory=1, visual=3). If int, a dict will be created with
        the id as string. If a list, all events with the IDs specified
        in the list are used. If None, the event_id is constructed from the
        EEGLAB (.set) file with each descriptions copied from `eventtype`.
    tmin : float
        Start time before event.
    baseline : None or tuple of length 2 (default (None, 0))
        The time interval to apply baseline correction.
        If None do not apply it. If baseline is (a, b)
        the interval is between "a (s)" and "b (s)".
        If a is None the beginning of the data is used
        and if b is None then b is set to the end of the interval.
        If baseline is equal to (None, None) all the time
        interval is used.
        The baseline (a, b) includes both endpoints, i.e. all
        timepoints t such that a <= t <= b.
    reject : dict | None
        Rejection parameters based on peak-to-peak amplitude.
        Valid keys are 'grad' | 'mag' | 'eeg' | 'eog' | 'ecg'.
        If reject is None then no rejection is done. Example::

            reject = dict(grad=4000e-13, # T / m (gradiometers)
                          mag=4e-12, # T (magnetometers)
                          eeg=40e-6, # uV (EEG channels)
                          eog=250e-6 # uV (EOG channels)
                          )
    flat : dict | None
        Rejection parameters based on flatness of signal.
        Valid keys are 'grad' | 'mag' | 'eeg' | 'eog' | 'ecg', and values
        are floats that set the minimum acceptable peak-to-peak amplitude.
        If flat is None then no rejection is done.
    reject_tmin : scalar | None
        Start of the time window used to reject epochs (with the default None,
        the window will start with tmin).
    reject_tmax : scalar | None
        End of the time window used to reject epochs (with the default None,
        the window will end with tmax).
    verbose : bool, str, int, or None
        If not None, override default verbose level (see mne.verbose).

    Notes
    -----
    .. versionadded:: 0.11.0

    See Also
    --------
    mne.Epochs : Documentation of attribute and methods.
    """
    @verbose
    def __init__(self, input_fname, events=None, event_id=None, tmin=0,
                 baseline=None,  reject=None, flat=None, reject_tmin=None,
                 reject_tmax=None, montage=None, verbose=None):
        from scipy import io
        eeg = io.loadmat(input_fname, struct_as_record=False,
                         squeeze_me=True)['EEG']

        if events is None and eeg.trials > 1:
            # first extract the events and construct an event_id dict
            event_type, event_latencies, unique_ev = [], [], []
            for ep in eeg.epoch:
                if not isinstance(ep.eventtype, string_types):
                    raise ValueError('An epoch can have only one event'
                                     ' in mne-python')
                else:
                    event_type.append(ep.eventtype)
                    event_latencies.append(ep.eventurevent)
                    if ep.eventtype not in unique_ev:
                        unique_ev.append(ep.eventtype)
                event_id = dict((ev, idx) for idx, ev in enumerate(unique_ev))
            # now fill up the event array
            events = np.zeros((eeg.trials, 3), dtype=int)
            for idx in range(eeg.trials):
                events[idx, 0] = event_latencies[idx]
                events[idx, 1:] = event_id[event_type[idx]]
        elif isinstance(events, string_types):
            events = read_events(events)

        logger.info('Extracting parameters from %s...' % input_fname)
        input_fname = op.abspath(input_fname)
        info = _get_info(eeg, montage)

        if event_id is None:  # convert to int to make typing-checks happy
            event_id = dict((ev, idx) for idx, ev in enumerate(unique_ev))

        for key, val in event_id.items():
            if val not in events[:, 2]:
                raise ValueError('No matching events found for %s '
                                 '(event id %i)' % (key, val))

        self._filename = input_fname
        if isinstance(eeg.data, string_types):
            basedir = op.dirname(input_fname)
            data_fname = op.join(basedir, eeg.data)
            data_fid = open(data_fname)
            data = np.fromfile(data_fid, dtype=np.float32)
            data = data.reshape((eeg.trials, eeg.nbchan, eeg.pnts), order="F")
        else:
            data = eeg.data
            data = data.transpose((2, 0, 1))

        assert data.shape == (eeg.trials, eeg.nbchan, eeg.pnts)
        tmin, tmax = eeg.xmin, eeg.xmax
        super(EpochsSet, self).__init__(info, data, events, event_id,
                                        tmin, tmax, baseline,
                                        reject=reject, flat=flat,
                                        reject_tmin=reject_tmin,
                                        reject_tmax=reject_tmax,
                                        verbose=verbose)
        logger.info('Ready.')
