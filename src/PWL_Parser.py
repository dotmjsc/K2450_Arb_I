"""
parses ltspice-style PWL texts into two plot-ready arrays
written by markus(a)schrodt.at
LICENSE: GPL-3.0-or-later
"""

import logging
import numpy as np
import mimetypes
from si_prefix import si_parse
import os


class PwlData:
    def __init__(self):
        self.values = []
        self.timestamps = []
        self.values_discrete = []
        self.timestamps_discrete = []

def discretize(timestamps, values, delta):
    """
    interpolate pwl data and make a discrete series
    :param timestamps: some timestamps
    :param values: the values for those timestamps
    :param delta: time step
    :return: timestamps and values, discrete and evenly timed
    """

    # check lengths
    if len(timestamps) != len(values):
        return None

    values_out = []
    timestamps_out = []

    for timestep in np.arange(0, max(timestamps), delta):
        timestamps_out.append(timestep)
        values_out.append(np.interp(timestep, timestamps, values))

    return timestamps_out, values_out

def PWL_parser(pwl_text_file, timestep):
    """
    Loads a LT-Spice styled PWL data file. Also creates a discrete series of samples.
    :param pwl_text_file: the file path
    :param timestep: the timestep for creating a discrete series
    :return: None in case of a fail
    """
    pwl_data = PwlData()

    # check if file exists
    if not os.path.exists(pwl_text_file):
        logging.error('PWL Parser: PWL file not found')
        return None

    # check if text file
    if not mimetypes.guess_type(pwl_text_file)[0] == 'text/plain':
        logging.error('PWL Parser: PWL file not in text format')
        return None

    with open(pwl_text_file) as file:
        lines = file.read().splitlines()

        # check if empty
        if len(lines) == 0:
            logging.error('PWL Parser: PWL file empty')
            return None

        time_last = 0

        for i, line in enumerate(lines):
            arguments = line.split()

            # check if two args per line
            if len(arguments) != 2 and len(arguments) != 0:
                logging.error('PWL Parser: PWL file argument format in line %d' % i)
                return None

            # only parse non-empty lines
            if len(arguments) != 0:
                time_read = si_parse(arguments[0])

                # detect if time argument is relative
                if arguments[0][0] == '+':
                    time_made = time_last + time_read

                else:
                    time_made = time_read

                pwl_data.timestamps.append(time_made)
                pwl_data.values.append(si_parse(arguments[1]))
                time_last = time_made

        pwl_data.timestamps_discrete, pwl_data.values_discrete = discretize(pwl_data.timestamps, pwl_data.values, timestep)

        logging.info('PWL Parser: PWL file load successful')
        logging.info('PWL Parser: Total PWL file run time: %0.3f s' % max(pwl_data.timestamps))
        logging.info('PWL Parser: Total SMU run time: %0.3f s' % max(pwl_data.timestamps_discrete))
        logging.info('PWL Parser: Nr of points: %d' % len(pwl_data.timestamps_discrete))

        return pwl_data

    logging.error('PWL file error')
    return None

if __name__ == '__main__':
    import os


    pwl_data_out = PWL_parser(os.path.join(os.path.dirname(__file__), 'test_pwl.txt'), 0.002)
    print(pwl_data_out.values)
    print(pwl_data_out.timestamps)
    print(pwl_data_out.values_discrete)
    print(pwl_data_out.timestamps_discrete)
