"""
A GUI for the Keithley 2450 sequenced current source
written by markus(a)schrodt.at
GUI Made with the fantastic PAGE Gui Generator
LICENSE: GPL-3.0-or-later
"""

import tkinter as tk
from tkinter.constants import *
from tkinter import filedialog
import K2450_Arb_I
import sys, os, csv, logging
from PWL_Parser import PWL_parser, PwlData
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from datetime import datetime
from K2450_pics import info_pic
from K2450_ArbCurrentSource import K2450_ArbCurrentSource, get_visa_devices
from K2450_Config import K2450_Config

K2450_SL = None
global_config = K2450_Config()

file_ready = False
pwl_data = PwlData()
canvas_plot = None

version_string = '1.1'
date_string = '19-Feb-2022'

class TextHandler(logging.Handler):
    """
    https://gist.github.com/moshekaplan/c425f861de7bbf28ef06
    https://beenje.github.io/blog/posts/logging-to-a-tkinter-scrolledtext-widget/
    """

    def __init__(self, text):
        logging.Handler.__init__(self)
        self.text = text
        self.text.tag_config('TIMESTAMP', foreground='gray')
        self.text.tag_config('INFO', foreground='black')
        self.text.tag_config('DEBUG', foreground='gray')
        self.text.tag_config('WARNING', foreground='orange')
        self.text.tag_config('ERROR', foreground='red')
        self.text.tag_config('CRITICAL', foreground='red', underline=1)

    def emit(self, record):
        msg = self.format(record)
        # strip any newlines
        msg = msg.rstrip('\n')
        def append():
            self.text.configure(state='normal')
            self.text.insert(tk.END, datetime.now().strftime("%Y-%m-%d %H:%M:%S "), 'TIMESTAMP')
            self.text.insert(tk.END, msg + '\n', record.levelname)
            self.text.configure(state='disabled')
            # Autoscroll to the bottom
            self.text.yview(tk.END)
        # This is necessary because we can't modify the Text from other threads
        self.text.after(0, append)

def create_widget_logger(filename, widged_handle):

    # Create textLogger
    text_handler = TextHandler(widged_handle)

    # Logging configuration
    logging.basicConfig(filename=filename,
                        level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    # Add the handler to logger
    logger = logging.getLogger()
    logger.addHandler(text_handler)

def quit_app():
    """
    For a safe exit
    :return:
    """
    global root, K2450_SL
    if K2450_SL is not None:
        del K2450_SL
    root.quit()
    root.destroy()
    exit()

def main():
    '''Main entry point for the application.'''
    global root, _top1, _w1
    root = tk.Tk()
    root.protocol('WM_DELETE_WINDOW', quit_app)
    # Creates a toplevel widget.
    _top1 = root
    _w1 = K2450_Arb_I.Toplevel1(_top1)

    titlestring = 'Keithley 2450 Arbitrary Current Source / Sink. Version: ' + version_string + ' | Build: ' + date_string
    _top1.title(titlestring)

    # create combined widget and text logger
    create_widget_logger('K2450_ArbSource.log', _w1.Scrolledtext1)

    logging.info("Startup successful - GUI ready")

    # load info picture from base64 data
    _img0 = tk.PhotoImage(data=info_pic)
    _w1.Label12.configure(image=_img0)

    # link canvas to a pyplot figure for global use
    global canvas_plot, canvas_figure
    canvas_figure = plt.figure(1)
    canvas_plot = FigureCanvasTkAgg(canvas_figure, master=_w1.Canvas1)
    NavigationToolbar2Tk(canvas_plot, _w1.Canvas1)
    canvas_plot.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

    refresh_visa_devices()

    # load default values:
    default_file = 'default.ini'

    if os.path.exists(default_file):
        logging.info("Loading default.ini")
        global_config.load_file(default_file)
    else:
        logging.info("No default.ini found")

    # set default values for UI elements
    make_ui_from_config()

    root.mainloop()

def K2450_open():
    """
    open the Keithley 2450 with the address chosen in the combobox
    :return:
    """
    global _w1, K2450_SL
    success = True
    if K2450_SL is not None:
        del K2450_SL
        K2450_SL = None
    try:
        K2450_SL = K2450_ArbCurrentSource(_w1.select_visa_adress.get())
    except:
        logging.error('K2450 device open error')
        success = False
    UiActivityUpdate()
    return success

def PWL_file_open():
    """
    invoked by the "File open" Button
    :return:
    """
    global _w1
    filetypes = (('text files', '*.txt'), ('All files', '*.*'))

    filename = filedialog.askopenfilename(
        title='Open file',
        filetypes=filetypes)

    if filename:
        if PWL_file_load(filename) is not False:
            _w1.var_pwl_file.set(filename)

def PWL_file_reload():
    """
    invoked by the "Reload" button
    :return: False if fail
    """
    global _w1
    return PWL_file_load(_w1.var_pwl_file.get())

def PWL_file_load(filename):
    """
    Load a PWL file
    :param filename: filename
    :return: False if case of fail
    """
    global _w1, file_ready, pwl_data

    logging.info("Loading pwl file: %s" % filename)
    pwl_data_parsed = PWL_parser(filename, float(_w1.spin_timesteps.get())/1000)
    if pwl_data_parsed is None:
        logging.error('PWL file load unsuccessful!')
        file_ready = False
        return False

    pwl_data = pwl_data_parsed

    # invert eventually, if checkbox is set
    if _w1.chk_invert.get() == 1:

        def Invert(lst):
            return [-i for i in lst]

        logging.info("PWL data inverted")
        pwl_data.values = Invert(pwl_data.values)
        pwl_data.values_discrete = Invert(pwl_data.values_discrete)

    plot_pwl_data()
    file_ready = True
    UiActivityUpdate()
    return True

def make_ui_from_config():
    """
    updates the UI based on the global config
    :return:
    """
    global _w1, global_config, file_ready, K2450_SL

    _w1.chk_invert.set(0)
    _w1.chk_autozero.set(0)
    _w1.chk_autonplcs.set(0)
    _w1.chk_autodelay.set(0)
    _w1.chk_uvlo_on.set(0)
    _w1.chk_4wire.set(0)
    _w1.chk_beep.set(0)
    _w1.chk_assure_timing.set(0)
    _w1.chk_autovrange.set(0)
    _w1.chk_autoirange.set(0)
    _w1.chk_protect_enable.set(0)

    if global_config.invert is True:
        _w1.chk_invert.set(1)

    if global_config.auto_zero is True:
        _w1.chk_autozero.set(1)

    if global_config.auto_nplc is True:
        _w1.chk_autonplcs.set(1)

    if global_config.auto_delay is True:
        _w1.chk_autodelay.set(1)

    if global_config.uvlo_enable is True:
        _w1.chk_uvlo_on.set(1)

    if global_config.four_wire is True:
        _w1.chk_4wire.set(1)

    if global_config.beep is True:
        _w1.chk_beep.set(1)

    if global_config.assure_timing is True:
        _w1.chk_assure_timing.set(1)

    if global_config.auto_meas_range is True:
        _w1.chk_autovrange.set(1)

    if global_config.auto_source_range is True:
        _w1.chk_autoirange.set(1)

    if global_config.protect_enable is True:
        _w1.chk_protect_enable.set(1)

    _w1.spin_timesteps.set(global_config.time_step * 1000)  # milliseconds
    _w1.spin_manualdelay.set(global_config.manual_delay * 1000)
    _w1.spin_uvlo.set(global_config.uvlo_voltage)
    _w1.spin_inital_delay.set(global_config.initial_delay)

    _w1.var_protect_box.set(float(global_config.protect_voltage))
    _w1.var_i_range_box.set(float(global_config.source_range))
    _w1.var_range_v_box.set(float(global_config.meas_range))

    _w1.spin_vlimit.set(global_config.limit_voltage)
    _w1.spin_nplcs.set(global_config.nplc)

    def reset_visa():
        _w1.select_visa_adress.set('Please select Visa Adress')
        global_config.visa_address = ""

    def reset_file():
        _w1.var_pwl_file.set("Please select file")
        global_config.file_name = ""

    if global_config.visa_address != "":
        _w1.select_visa_adress.set(global_config.visa_address)
        if K2450_open() is False:
            logging.warning('Config Load: VISA address invalid -> reset')
            reset_visa()
    else:
        if K2450_SL is None:
            reset_visa()

    if global_config.file_name != "":
        _w1.var_pwl_file.set(global_config.file_name)
        if PWL_file_reload() is False:
            logging.warning('Config Load: PWL data file invalid -> reset')
            reset_file()
    else:
        if file_ready is False:
            reset_file()

    UiActivityUpdate()

def make_config_from_ui():
    """
    reads the ui into the global config instance
    :return:
    """
    global _w1, global_config

    if _w1.chk_autozero.get() == 1:
        logging.debug('UI Cfg: autozero on')
        global_config.auto_zero = True
    else:
        logging.debug('UI Cfg: autozero off')
        global_config.auto_zero = False

    if _w1.chk_autodelay.get() == 1:
        logging.debug('UI Cfg: autodelay on')
        global_config.auto_delay = True
    else:
        logging.debug('UI Cfg: autodelay off')
        global_config.auto_delay = False

    if _w1.chk_uvlo_on.get() == 1:
        logging.debug('UI Cfg: UVLO on')
        global_config.uvlo_enable = True
    else:
        logging.debug('UI Cfg: UVLO off')
        global_config.uvlo_enable = False

    if _w1.chk_protect_enable.get() == 1:
        logging.debug('UI Cfg: Protect enable')
        global_config.protect_enable = True
    else:
        logging.debug('UI Cfg: Protect disable')
        global_config.protect_enable = False

    if _w1.chk_autovrange.get() == 1:
        logging.debug('UI Cfg: Auto Measurement Range')
        global_config.auto_meas_range = True
    else:
        logging.debug('UI Cfg: Manual Measurement Range')
        global_config.auto_meas_range = False

    if _w1.chk_autoirange.get() == 1:
        logging.debug('UI Cfg: Auto Source Range')
        global_config.auto_source_range = True
    else:
        logging.debug('UI Cfg: Manual Source Range')
        global_config.auto_source_range = False

    if _w1.chk_assure_timing.get() == 1:
        logging.debug('UI Cfg: Timing check enabled')
        global_config.assure_timing = True
    else:
        logging.debug('UI Cfg: Assure timing disabled')
        global_config.assure_timing = False

    if _w1.chk_4wire.get() == 1:
        logging.debug('UI Cfg: 4 wire ON')
        global_config.four_wire = True
    else:
        logging.debug('UI Cfg: 4 wire OFF')
        global_config.four_wire = False

    global_config.uvlo_voltage = float(_w1.spin_uvlo.get())
    logging.debug('UI Cfg: UVLO value = %0.2f V' % global_config.uvlo_voltage)

    global_config.manual_delay = float(_w1.spin_manualdelay.get()) / float(1000)  # milliseconds
    logging.debug('UI Cfg: source delay = %0.4f s' % global_config.manual_delay)

    global_config.protect_voltage = float(_w1.var_protect_box.get())
    logging.debug('UI Cfg: Protect = %d V' % global_config.protect_voltage)

    global_config.limit_voltage = float(_w1.spin_vlimit.get())
    logging.debug('UI Cfg: voltage limit = %0.2f V' % global_config.limit_voltage)

    global_config.meas_range = float(_w1.var_range_v_box.get())
    logging.debug('UI Cfg: voltage limit = %0.2f V' % global_config.meas_range)

    global_config.source_range = float(_w1.var_i_range_box.get())
    logging.debug('UI Cfg: voltage limit = %0.2f V' % global_config.source_range)

    global_config.time_step = float(_w1.spin_timesteps.get()) / float(1000)  # milliseconds
    logging.debug('UI Cfg: timestep = %0.4f s' % global_config.time_step)

    if _w1.chk_autonplcs.get() == 1:
        logging.debug('UI Cfg: Auto NPLC on')
        global_config.auto_nplc = True
    else:
        logging.debug('UI Cfg: Auto NPLC off')
        global_config.auto_nplc = False

    global_config.nplc = float(_w1.spin_nplcs.get())
    logging.debug('UI Cfg: nplc = %0.2f s' % global_config.initial_delay)

    global_config.initial_delay = float(_w1.spin_inital_delay.get())
    logging.debug('UI Cfg: initial delay = %0.2f s' % global_config.initial_delay)

    if _w1.chk_beep.get() == 1:
        logging.debug('UI Cfg: Beep on')
        global_config.beep = True
    else:
        logging.debug('UI Cfg: Beep off')
        global_config.beep = False

    if _w1.chk_invert.get() == 1:
        logging.debug('UI Cfg: Invert on')
        global_config.invert = True
    else:
        logging.debug('UI Cfg: Invert off')
        global_config.invert = False

    # if the default text is not set, file or address should be valid
    if _w1.select_visa_adress.get() != 'Please select Visa Adress':
        global_config.visa_address = _w1.select_visa_adress.get()
    if _w1.var_pwl_file.get() != 'Please select file':
        global_config.file_name = _w1.var_pwl_file.get()

def clear_plot():
    global canvas_plot
    plt.figure(1)
    plt.clf()
    canvas_plot.draw()

def plot_pwl_data():
    global canvas_plot
    logging.info("Plotting PWL data")
    clear_plot()
    plt.xlabel('Time (s)')
    plt.ylabel('SMU current (A)')
    plt.title('PWL file (with discrete Steps)')
    plt.plot(pwl_data.timestamps, pwl_data.values, color = 'blue', linewidth=2)
    # dotted plot of the discretized PWL waveform
    plt.scatter(pwl_data.timestamps_discrete, pwl_data.values_discrete, color = 'darkred')
    plt.grid()
    plt.tight_layout()
    canvas_plot.draw()

def plot_results():
    """
    plot measured results
    :return:
    """
    global _w1
    global canvas_plot
    logging.info("Plotting Measurements")

    if K2450_SL is not None:
        results = K2450_SL.return_results()
        if results is None:
            logging.error("Plotting Measurements: data empty")
            clear_plot()
            return

        timestamps = results['timestamps']
        voltages = results['voltages']
        currents = results['currents']

        plt.figure(1)
        plt.clf()
        ax1 = canvas_figure.add_subplot(111)

        # plot the sourced currents in blue
        color = 'blue'
        ax1.set_xlabel('time (s)')
        if _w1.chk_steppy_currents.get() == 1:
            # steppy plot for longer timesteps
            ax1.step(timestamps, currents, where='post', color=color)
        else:
            ax1.plot(timestamps, currents, color=color)
        ax1.tick_params(axis='y', labelcolor=color)

        # plot the voltages on a second axis
        ax2 = ax1.twinx()
        color = 'darkred'
        ax2.plot(timestamps, voltages, color=color)
        ax2.tick_params(axis='y', labelcolor=color)

        ax1.autoscale(enable=True, axis='y', tight=None)
        ax2.autoscale(enable=True, axis='y', tight=None)

        ax2.set_zorder(1)  # voltages are in front

        plt.grid()
        plt.title('Run Results')
        ax1.set_xlabel("Time (s)")
        ax1.set_ylabel(r"Current sourced (A)")
        ax2.set_ylabel(r"Voltage measured (V)")
        plt.tight_layout()

        canvas_plot.draw()

def refresh_visa_devices():
    """
    Read available visa devices into the combobox
    :return:
    """
    global _w1
    logging.info('Refresh Visa devices')
    _w1.TCombobox1['values'] = get_visa_devices()

    sys.stdout.flush()

def Run_Sequence(simulate = False):
    """
    Invoked by the "RUN" button.
    :param simulate if True, only the values are loaded, but the run will be aborted
    """
    if K2450_SL is None:
        logging.error('Cant load settings, K2450 not ready')
        return False
    if file_ready is False:
        logging.error('Cant load settings, PWL data not ready')

    make_config_from_ui()  # update from UI
    K2450_SL.config = global_config
    K2450_SL.load_data_points(pwl_data.values_discrete)

    run_status = K2450_SL.run_sequence(simulate)
    if run_status is False:
        logging.error('Sequence Run error. Run aborted!')
    elif run_status == 0:
        logging.info('Sequence Run successful')
    else:
        logging.warning('Sequence Run with %d warnings!' % run_status)

    if not simulate:
        plot_results()
    UiActivityUpdate()
    sys.stdout.flush()

def UiActivityUpdate():
    """
    processes states of GUI elements by checkbox settings
    writes info into the Infobox
    :return:
    """
    global _w1

    # delete info text
    _w1.Infobox.config(state='normal')
    _w1.Infobox.delete('1.0', END)

    if _w1.chk_autodelay.get() == 1:
        _w1.Spinbox1['state'] = 'disabled'
    else:
        _w1.Spinbox1['state'] = 'normal'

    if _w1.chk_autonplcs.get() == 1:
        _w1.Spinbox6['state'] = 'disabled'
    else:
        _w1.Spinbox6['state'] = 'normal'

    if _w1.chk_autovrange.get() == 1:
        _w1.TCombobox4['state'] = 'disabled'
    else:
        _w1.TCombobox4['state'] = 'normal'

    if _w1.chk_autoirange.get() == 1:
        _w1.TCombobox3['state'] = 'disabled'
    else:
        _w1.TCombobox3['state'] = 'normal'

    if _w1.chk_protect_enable.get() == 1:
        _w1.TCombobox2['state'] = 'normal'
    else:
        _w1.TCombobox2['state'] = 'disabled'

    # check if run ready
    if K2450_SL is not None and file_ready is not False:
        _w1.Button2['state'] = 'active'
        _w1.Btn_Simulate['state'] = 'active'
    else:
        _w1.Button2['state'] = 'disabled'
        _w1.Btn_Simulate['state'] = 'disabled'

    if _w1.chk_uvlo_on.get() == 1:
        _w1.Spinbox2['state'] = 'normal'
    else:
        _w1.Spinbox2['state'] = 'disabled'

    if file_ready is True:
        _w1.Button6['state'] = 'normal'
        _w1.Infobox.insert(tk.END, 'PWL data ready: %d points \n' % len(pwl_data.timestamps_discrete))
    else:
        _w1.Button6['state'] = 'disabled'
        _w1.Infobox.insert(tk.END, 'PWL data not ready\n')
        clear_plot()

    if K2450_SL is not None:
        _w1.Infobox.insert(tk.END, 'SMU ready\n')
    else:
        _w1.Infobox.insert(tk.END, 'SMU not ready\n')

    # I have to do it that way else the method results_valid() might be called on a None
    results_valid = False
    if K2450_SL is not None:
        if K2450_SL.results_valid():
            results_valid = True

    if results_valid is True:
        _w1.Button5['state'] = 'normal'
        _w1.Button7['state'] = 'normal'
        _w1.Infobox.insert(tk.END, 'Measurements ready: %d points\n'  % len(K2450_SL.return_results()['timestamps']))
    else:
        _w1.Button5['state'] = 'disabled'
        _w1.Button7['state'] = 'disabled'
        _w1.Infobox.insert(tk.END, 'Measurements not ready\n')

    _w1.Infobox.config(state='disabled')
    sys.stdout.flush()

def btn_load_config():
    """
    Invoked by the "Load config" button
    :return:
    """
    global _w1
    filetypes = (('ini files', '*.ini'),)

    filename = filedialog.askopenfilename(
        title='Open file',
        filetypes=filetypes)

    if filename:
        # store actual settings (transparent)
        make_config_from_ui()

        logging.info('Load Config: %s' % filename)
        global_config.load_file(filename)

        make_ui_from_config()

def btn_save_config():
    """
    Invoked by the "Save config" button
    :return:
    """
    make_config_from_ui()

    filename = filedialog.asksaveasfilename(
        title='Save file',
        defaultextension='.ini',
        filetypes=(('ini files', '*.ini'),))

    if filename:
        logging.info('Save Config as: %s' % filename)
        global_config.save_file(filename)

def btn_export_csv():
    """
    Invoked by the "Save CSV" button
    :return:
    """
    filename = filedialog.asksaveasfilename(
        title='Save file',
        defaultextension='.csv',
        filetypes=(('csv files', '*.csv'),('txt files', '*.txt')))

    if filename != "":
        logging.info('Save CSV as: %s' % filename)
        # check if data is available
        if K2450_SL is not None:
            results = K2450_SL.return_results()
            if results is None:
                logging.error("CSV export: data empty")
                return

            timestamps = results['timestamps']
            voltages = results['voltages']
            currents = results['currents']

            with open(filename, 'w', encoding='UTF8', newline='') as file_csv:
                header = ['Timestamp', 'Current', 'Voltage']
                writer = csv.writer(file_csv)
                writer.writerow(header)
                for i, timestamp in enumerate(timestamps):
                    writer.writerow([timestamp, currents[i], voltages[i]])

def Run_Simulate(*args):
    Run_Sequence(simulate = True)

if __name__ == '__main__':
    K2450_Arb_I.start_up()





