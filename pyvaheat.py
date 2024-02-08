import json
import logging
import serial
from serial.tools import list_ports
import signal
import sys
import re
from typing import List, Dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
logger.addHandler(ch)
formatter_iso8601 = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
ch.setFormatter(formatter_iso8601)

class Vaheat:
    """
    Wrapper class of serial communication to VAHEAT

    Attributes:
        port       (str): Port to connect VAHEAT
        info      (dict): Device info
        baud_rate  (int): Baud rate for serial communication. maximum: 921600
        timeout    (int): Read timeout in seconds.
        serial  (Serial): Serial object
        API_CMD   (dict): commands and parameters for VAHEAT API
        CLI_CMD   (dict): commands and parameters for CLI
    """
    API_CMD = {
        "get_info":None,
        "get_status":None,
        "get_settings":None,
        "get_streaming":None,
        "get_profile":"profile_number,step",
        "start_heating":"mode,power,temperature,duration,profile_number,ignore_limit_error",
        "stop_heating":None,
        "do_reset":"all,profiles,settings,pid,profile_number",
        "set_keylock":"(bool)",
        "set_settings":"brightness,haptic_strength,temperature_limit,limit_enabled,pid{p,i,d}",
        "set_streaming":"mode,rate,time,remaining,onoff,temperature,setpoint,power,profile_step,resistance",
        "set_mode":"mode,power,temperature,duration,profile_number",
        "set_profile":"profile_number,name,steps,duration,rate,setpoint",
        }
    CLI_CMD = {
        "connect":None,
        "disconnect":None,
        "port":"ex. COM3, /dev/ttyUSB*, /dev/ttyACM*",
        "baud_rate":"9600, 14400, 19200, 38400, 57600, 115200, 230400, 460800, 921600",
        "start_streaming":"once or continuous (str)",
        "raw":None,
        "read":None,
        "read_all":None,
        "write":None,
        "exit":None,
    }

    def __init__(self, port=None, baud_rate=115200, timeout=0.5):
        """
        Initialize the USB device with specified serial port settings.
        Try to find the first VAHEAT device if the port is not specified.
        Send get_info command to acquire info of the connected device.

        Args:
            port (str, optional): Serial port (e.g., 'COM4'). Defaults to None
            baud_rate (int): Baud rate for serial communication. maximum: 921600
            timeout (int): Read timeout in seconds.

        Raises:
            OSError: Raised if the peripheral device with the specified port
                     cannot be found or the connection cannot be established.
        """
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial = None
        self.info = None
        self.read_raw = ''
        self.write_raw = ''
        self.error = ''

    def connect(self) -> bool:
        """Open the serial connection."""
        if self.port is None:
            devices = Vaheat.find_ports()
            if not devices:
                raise OSError("No connected VAHEAT devices.")
            if len(devices) >= 1:
                self.port = devices[0]
                logging.info(f"{self.port} port is set.")
            if len(devices) > 1:
                logging.info("Mulpiple devices are connected. Specify port to handle.")
        try:
            self.serial = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            logging.info(f"Connected to {self.port}")
            self.info = self.get_info()
            return self.serial.is_open
        except serial.SerialException as e:
            logging.error(f"Error opening serial port {self.port}: {e}")

    def disconnect(self) -> None:
        """Close the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            logging.info(f"Disconnected from {self.port}")

    def get_info(self) -> dict:
        """The get_info command will reply with information about your device."""
        info = self._get('get_info')
        if info:
            self.info = info['data']
            return self.info
        return None

    def get_status(self) -> dict:
        """The get_status command will repoly with information about the status of your device."""
        status = self._get('get_status')
        if status:
            return status['data']
        return None

    def get_settings(self) -> dict:
        """The get_settings command will repoly with the settings stored on your device."""
        settings = self._get('get_settings')
        if settings:
            return settings['data']
        return None
    
    def get_streaming(self) -> dict:
        """
        The get streaming command will reply with the streaming settings stored on your device.

        Note:
            ! Since current VAHEAT device returns wrong JSON format missing comma, raw string is manupilated.
        """
        self.write(self._json_str('get_streaming'))
        raw_str = self.read_all_lines()

        # Manipulate raw string
        corrected = self._add_commas(raw_str)
        response = self._json2dict(corrected)
        if response is None:
            return None
        response['data']['rate'] = int(response['data']['rate'])  # type(rate) should be int
        return response['data']

    def get_profile(self, config) -> dict:
        """
        The get_profile command will reply with the requested profile or profile step
        as stored on your device.

        Args:
            config (dict): dict of parameters
        
        Note:
            ! Since current VAHEAT device returns wrong JSON format missing comma, raw string is manupilated.

            keys and paramters
            profile_number (int): Number of profile
            step (int, optional): Number of step
        """
        if not config or not 'profile_number' in config:
            return None
        self.write(self._json_str('get_profile', data=config))
        raw_str = self.read_all_lines()
        # When profile number is specified, correction is needed.
        if 'step' in config:
            corrected = self._add_commas(raw_str)
            response = self._json2dict(corrected)
        else:
            response = self._json2dict(raw_str)
        if not response:
            return None
        return response['data']

    def start_heating(self, config) -> bool:
        """
        The 'start_heating' command allows you to change the operating mode
        of the device and start the heating process.

        Returns:
            bool: success
        Args:
            config (dict): dict of parameters
        
        Note:
            keys and parameters
            mode                     (str): Device mode. (AUTO/DIRECT/SHOCK/PROFILE), default: auto
            power        (float, optional): Relative power (%) in DIRECT and SHOCK mode. Defaults 0.1%
            temperature  (float, optional):Temperature setoing in AUTO mode. Defaults 25 degC.
            duration     (float, optional): Shock duration in SHOCK mode [0.1-9999]
            profile_number (int, optional): Profile selection [1-9] in PROFILE mode. Defaults -1
        """
        if not config:
            return False
        alarm = self.get_alarm()
        if not alarm or alarm != "NO_ALARM":
            logging.error(f"ALARM status: {alarm}. Check hardware.")
            return False
        mode = config.get('mode','auto')
        d = {'mode':mode}
        if mode.lower() == 'auto':
            if 'temperature' in config:
                d['temperature'] = config['temperature']
        elif mode.lower() == "direct":
            if 'power' in config:
                d['power'] = config['power']
        elif mode.lower() == 'shock':
            if 'power' in config:
                d['power'] = config['power']
            if 'duration' in config:
                d['duration'] = config['duration']
        elif mode.lower() == 'profile':
            if 'profile_number' in config:
                profile_number = config['profile_number']
                if profile_number < 1 or profile_number > 9:
                    logging.error(f"Profile number exceeded. {profile_number}")
                    return False
                d['profile_number'] = profile_number
            if 'ignore_limit_error':
                d['ignore_limit_error'] = config['ignore_limit_error']

        self.write(self._json_str('start_heating',data=d))
        if self._is_success(self._json2dict(self.read_all_lines())):
            logging.info(f"Heating started by {mode} mode.")
            return True
        return False

    def get_alarm(self) -> str:
        """Return current alarm condition"""
        status = self.get_status()
        if status:
            return status['alarm']
        return None

    def stop_heating(self) -> bool:
        """ The stop_heating command allows you to stop the heating process immediately."""
        success = self._is_success(self._get('stop_heating'))
        logging.info("Heating stopped.")
        return success

    def start_streaming(self, mode:str='continuous') -> bool:
        """
        Start streaming with current streaming settings.
        Only 'continuous'(default) or 'once' mode is accepted.

        Args:
            mode (str, optional): continuous or once
        """
        alarm = self.get_alarm()
        if not alarm or alarm != "NO_ALARM":
            logging.error(f"ALARM status: {alarm}. Check hardware.")
            return False
        if mode == 'continuous' or mode == 'once':
            return self.set_streaming({'mode':mode})
        else:
            return False

    def stop_streaming(self) -> bool:
        """
        Stop streaming
        """
        return self.set_streaming({'mode':'off'})

    def do_reset(self, config:dict) -> bool:
        """
        do_reset command allows you to reset parts of your device.
        
        Returns:
            bool: succeeded
        Args:
            config (dict): configs where to be reset.
        Note:
            keys and parameters
            all           (bool): Reset everything
            profiles      (bool): Reset profiles
            settings      (bool): Reset settings
            pid           (bool): reset PID gains
            profile_number (int): Number of the profile to reset (1-9)    
        """
        if len(config) == 0:
            return False
        d = {}
        if "alL" in config and config["all"]:
            d['all'] = True
        else:
            d = config
        self.write(self._json_str('do_reset', config))
        return self._is_success(self._json2dict(self.read_all_lines()))

    def set_keylock(self, keylock:bool) -> bool:
        """
        set_keylock command allows you to set or release the keylock by True/False
        
        Args:
            keylock (bool): lock or unlock
        """
        self.write(self._json_str('set_keylock', data=keylock))
        success = self._is_success(self._json2dict(self.read_all_lines()))
        if success:
            if keylock:
                logging.info(f"Device is key-locked.")
            else:
                logging.info(f"Device is key-unlocked.")
        return success

    def set_settings(self, config:dict) -> bool:
        """
        Set settings defined by dictionary on your device. (See manual 6.3.3)
        The dictionary is avaiable get_settings()

        Args:
            config (dict): parameters for device settings
        
        Note:
            keys and parameters
            brightness          (int): brightness for display and keys (0-10)
            haptic_strength     (int): strength of vibration motor for touch feedback (0-5)
            temperature_limit (float): Maximum temperature limit (PID may overshoot).
            limit_enabled      (bool): Whether the limit is activated
            pid (dict):
                p               (int): P-gain, defaults to 150.
                i               (int): I-gain, defaults to 70.
                d               (int): D-gain, defaults to 0.
        """
        if not config:
            return False
        cmd = self._json_str('set_settings', data=config)
        self.write(cmd)
        return self._is_success(self._json2dict(self.read_all_lines()))

    def set_streaming(self, config:dict) -> bool:
        """
        set_streaming command allows you to change the streaming settings stored on your device.
        The dictionary is avaiable get_settings()

        Args:
            config(dict): parameters for streaming

        Note:
            keys and parameters
            mode         (str): Streaming mode (off/once/continuous)
            rate         (int): Rate of updates per second (1,2,5,10,20)
            Whether to stream of the following data
            time         (bool): time since start in seconds
            remaining    (bool): remaining time of shock or profile step
            onoff        (bool): the status of the heater
            temperature  (bool): temperature in deg.C
            setpoint     (bool): setpoing in deg.C
            power        (bool): power in mW.
            profile_step (bool): Active number and step of the profile
            resistance   (bool): sensor resistance in Ohm
        """
        if not config:
            return False
        cmd = self._json_str('set_streaming', data=config)
        self.write(cmd)
        return self._is_success(self._json2dict(self.readline()))

    def set_mode(self, config) -> bool:
        """
        set_mode allows you to change the operating mode of the device.config

        Args:
            config(dict): parameters for mode
        
        Note:
            keys and parameters
            mode (str)          : Device mode (AUTO/DIRECT/SHOCK/PROFILE)
            power        (float): Relative power (%) in DIRECT/SHOCK mode
            temperature  (float): Temperature setpoint deg.C in AUTO mode
            duration     (float): Shock duration in seconds (0.1-9999) in SHOCK mode
            profile_number (int): Profile selection (1-9) in PROFILE mode
        """
        if 'mode' not in config:
            raise ValueError('No mode key in config.')

        mode = config['mode'].lower()
        d = {'mode':mode}
        if mode == 'auto':
            if 'temperature' in config:
                d['temperature'] = config['temperature']
        elif mode == 'direct':
            if 'power' in config:
                d['power'] = config['power']
        elif mode == 'shock':
            if 'power' in config:
                d['power'] = config['power']
            if 'duration':
                d['duration'] = config['duration']
        elif mode == 'profile':
            if 'profile_number' in config:
                d['profile_number'] = config['profile_number']
        else:
            raise ValueError(f"Mode {mode} is not allowed.")
        self.write(self._json_str('set_mode', data=d))
        response = self._json2dict(self.read_all_lines())
        return response and self._is_success(response)

    def set_profile(self, profile) -> bool:
        """
        Set profile
        
        Args:
            profile (dict): dict of profile
        
        Note:
            keys and parameters
            profile_number (int): Number of the profile slot to write to. (1-9)
            name (str): User defined name of the profile (up to 47 chars)
            steps (list): List of steps
                [{
                    duration (float): Length of the requested step in seconds.
                    rate (float): Rate of change, starting from the previous step setpoint degC/s
                    setpoint (float): Setpoint to hold in this step.
                },]
        """
        if not profile:
            return None
        self.write(self._json_str('set_profile',profile))
        return self._is_success(self._json2dict(self.read_all_lines()))

    def _json2dict(self, json_str:str) -> dict:
        """Try to convert from JSON str to dict"""
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logging.warning(f"JSON decoding error: {e.msg} at {e.pos}\nInput data: {e.doc}")
            return None

    def readline(self) -> str:
        """
        Read a JSON line from the serial port buffer.

        Returns:
            str: Returned JSON line
        """
        if self.serial and self.serial.is_open:
            try:
                json_str = self.serial.readline().decode('utf-8').rstrip()
                self.read_raw = json_str
                return json_str
            except Exception as e:
                logging.error(f"Error in reading data: {e}")
        return ''

    def read_all_lines(self) -> str:
        """
        Read JSON string lines from the serial port buffer.

        Returns:
            str: Returned JSON lines        
        """
        if self.serial and self.serial.is_open:
            try:
                lines = ''
                while True:
                    l = self.serial.readline().decode('utf-8')
                    if not l:
                        break  # No more data, exit loop
                    lines += l
                json_str = lines.rstrip()
                self.read_raw = json_str
                return json_str
            except Exception as e:
                logging.error(f"Error in reading all lines: {e}")
        return ''

    def write(self, json_str) -> bool:
        """
        Write JSON string to the serial port.

        Args:
            data (str): JSON string to write
        
        Returns:
            bool: Data sent
        """
        if not json_str:
            return False
        if self.serial and self.serial.is_open:
            self.write_raw = json_str
            try:
                self.serial.write(json_str.encode())
                return True
            except Exception as e:
                logging.error(f"Error in writing data: {e}")
        else:
            logging.error("Device is not connected.")
        return False
    
    def _get(self, cmd) -> dict:
        """
        Get response after writing cmd

        Args:
            cmd(str): string of command
        """
        if self.serial and self.serial.is_open:
            if self.write(self._json_str(cmd)):  # Write get_XXX without data
                data = self._json2dict(self.read_all_lines())  # Read data in buffer as dict
                return data
        else:
            msg = "Connection is not open."
            logging.error(msg)
        return None

    def _is_success(self, d:dict) -> bool:
        """
        Check the previous command was accepted successfully.

        Args:
            response (dict): Response dict from device

        Returns:
            bool: Success
        """
        if not d:  # None or empty dict
            return False
        if 'success' in d and not d['success']:
            logging.error(d)
            self.error = str(d)
            return False
        if 'error' in d:
            logging.error(d)
            self.error = str(d)
            return False
        return True

    def _json_str(self, cmd:str, data=None) -> str:
        """
        Returns encoded str to send

        Args:
            cmd             (str): Command to send. It should be in allowed API_CMD
            data (dict, optional): Parameters dict. Defaults to None sending 'true' as value

        Returns:
            str: Encoded JSON string. Returns None when cmd is not in API_CMD.
        """
        if cmd not in self.API_CMD:
            logging.error("command not allowed.")
            return None
        if data is None:
            data = True
        return json.dumps({cmd:data})

    @staticmethod
    def find_ports() -> List[str]:
        """
        Find VAHEAT devices connected.
        
        Returns:
            list: Port name connected to VAHEAT
        """
        devices = []
        ports = serial.tools.list_ports.comports()
        for port, desc, hwid in sorted(ports):
            if "VID:PID=0483:5740" in hwid: # vendor ID and product ID of VAHEAT
                devices.append(port)
        return devices

    def __del__(self):
        """
        Destructor to ensure the serial connection is closed.
        """
        self.disconnect()

    def _add_commas(self, json_string):
        """
        Current VAHEAT device respond irregular JSON format missing commas by 'get_streaming' command
        """
        # Splitting the string into lines
        pat = ".*[{}:\[\]]$"
        lines = json_string.split('\n')
        corrected_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Check if the line ends with an opening or closing brace, or contains "data:":
            if stripped_line and not re.search(pat, stripped_line):
                # Add a comma at the end if it's missing
                if not stripped_line.endswith(','):
                    line = line.rstrip() + ','
            corrected_lines.append(line)
            corrected_json_string = '\n'.join(corrected_lines)
        # Remove the last comma
        reversed_s = corrected_json_string[::-1]  # Reverse the string
        corrected_s = reversed_s.replace(',', '', 1)  # Replace the first (actually last) comma found
        return corrected_s[::-1]  # Reverse the string back to original order

    def __str__(self):
        if self.serial.is_open:
            return 'VAHEAT ({self.port}, connected)'
        else:
            return 'VAHEAT ({self.port}, not connected)'

"""
CLI methods and main()
"""
global _vh, show_raw
_vh = Vaheat()
show_raw = False

def toggle_raw():
    global show_raw
    if show_raw:
        show_raw = False
        print("Show raw mode: OFF")
    else:
        show_raw = True
        print("Show raw mode: ON")

def _is_running_in_notebook():
    if "ipykernel" in sys.modules:
        return True
    if "IPython" in sys.modules:
        try:
            from IPython import get_ipython
            if "IPKernelApp" in get_ipython().config:
                return True
        except Exception as e:
            pass
    return False

def _do_exit():
    """Exit safe"""
    if _vh and _vh.serial and _vh.serial.is_open:
        _vh.disconnect()
        print("Device disconnected.")
    print("Exiting program. Bye!")
    if _is_running_in_notebook():
        raise SystemExit
    else:
        sys.exit(0)

def _input_params(msg="") -> dict:
    """
    Prompt parmeters by JSON str to convert to dict

    Args:
        msg(str): hints for parameters
    Returns:
        dict: parameters from JSON string
    """
    try:
        if msg:
            print(msg)
        s = input(prompt(input_type=f'JSON'))
        ss = s.replace("'",'"').replace("True","true").replace("False","false")
        return _vh._json2dict(ss)
    except EOFError:
        logging.error("EOF error with {s}")
    return None

def port():
    """Change Port name"""
    global _vh
    print(f"Current port is {_vh.port}")
    print("Enter port name to change.")
    port = input(prompt(input_type="port name"))
    if port and port != _vh.port:
        _vh.disconnect()
        _vh.port = port
        _vh.connect()

def baud_rate():
    """Change Baud rate"""
    global _vh
    print(f"Current baud_rate is {_vh.baud_rate}")
    baud_rate = input(prompt(input_type=Vaheat.CLI_CMD['baud_rate']))
    if baud_rate:
        if int(baud_rate) != _vh.baud_rate:
            _vh.disconnect()
            _vh.baud_rate = int(baud_rate)
            _vh.connect()

def start_heating():
    """start_heating by CLI"""
    return _vh.start_heating(_input_params(msg=Vaheat.API_CMD["start_heating"]))

def start_streaming() -> bool:
    """Start streaming by CLI"""
    return _vh.start_streaming(input(prompt(input_type=Vaheat.CLI_CMD['start_streaming'])))

def set_keylock() -> bool:
    """set_keylock by CLI"""
    s = input(prompt(input_type=Vaheat.API_CMD['set_keylock']))
    if s.lower() == "true":
        return _vh.set_keylock(True)
    elif s.lower() == "false":
        return _vh.set_keylock(False)

def get_profile() -> bool:
    config = {}
    num = input("Enter profile_number (1-9): ")
    if not num.isdigit() or (not 1 <= int(num) <= 9):
        return False 
    config['profile_number'] = int(num)    

    step = input("Step (1-20 or empty for all steps): ")
    if not step:  # empty
        return _vh.get_profile(config)
    if step.isdigit() and (1 <= int(step) <= 20):
        config['step'] = int(step)
        return _vh.get_profile(config)
    return None

def set_settings() -> bool:
    """set_settings by CLI"""
    return _vh.set_settings(_input_params(msg=Vaheat.API_CMD["set_settings"]))

def set_streaming() -> bool:
    """set_streaming by CLI"""
    return _vh.set_streaming(_input_params(msg=Vaheat.API_CMD["set_streaming"]))

def set_mode() -> bool:
    """set_mode"""
    return _vh.set_mode(_input_params(msg=Vaheat.API_CMD["set_mode"]))

def set_profile() -> bool:
    """set_profile"""
    return _vh.set_profile(_input_params(msg=Vaheat.API_CMD["set_profile"]))

def do_reset() -> bool:
    """do_reset by CLI"""
    print("Reset erases current parameters. Get & write down those parameters.")
    yn = input("Are you sure to proceed reset ? (Y/[N])")
    if yn.lower() == 'y':
        _vh.do_reset(_input_params(msg=Vaheat.API_CMD["do_reset"]))
    else:
        return False

def read() -> str:
    """Read raw line from buffer"""
    return _vh.readline()

def read_all() -> str:
    """Read all raw lines from buffer"""
    return _vh.read_all_lines()

def write() -> str:
    """Write raw line to device"""
    s = input("Enter JSON str to write: ")
    return _vh.write(s)

def error() -> str:
    """The latest error message"""
    return _vh.error

def unknown_command() -> str:
    """Unknown command"""
    print("Unknown command.")
    return

def prompt(input_type:str=None) -> str:
    """
    Returns prompt
    * General command input (no device connected): >
    * After connecting to "Device1": [Device1]>
    * If input_type is set, it is inserted like [Device1:JSON]>
    """
    if _vh.serial is None or not _vh.serial.is_open:
        return '\u2668 >'
    elif input_type:
        return f'\u2668 [{_vh.info["serial_number"]}:{input_type}]>'
    else:
        return f'\u2668 [{_vh.info["serial_number"]}]>'

def main():
    # Keyboard interruption handler (CTRL-C)
    signal.signal(signal.SIGINT, lambda signal, frame: _do_exit())
    print(f"[[VAHEAT CLI]]\n-------------------")
    ports = Vaheat.find_ports()
    if len(ports) > 0:
        ports_s = ','.join(ports)
        print(f"Avilable connected VAHEAT at {ports_s} port.")
    else:
        print(f"VAHEAT device was not found.")
        _do_exit()

    cli_commands = {
        "connect" : _vh.connect,
        "disconnect" : _vh.disconnect,
        "port": port,
        "baud_rate": baud_rate,
        "get_info": _vh.get_info,
        "get_status": _vh.get_status,
        "get_settings": _vh.get_settings,
        "get_streaming": _vh.get_streaming,
        "get_profile": get_profile,
        "start_heating": start_heating,
        "stop_heating": _vh.stop_heating,
        "start_streaming": start_streaming,
        "stop_streaming": _vh.stop_streaming,
        "do_reset": do_reset,
        "set_keylock": set_keylock,
        "set_settings": set_settings,
        "set_streaming": set_streaming,
        "set_mode": set_mode,
        "set_profile": set_profile,
        "raw": toggle_raw,
        "error": error,
        "read": read,
        "read_all": read_all,
        "write": write,
        "exit": _do_exit,
    }

    while True:
        try:
            user_command = input(prompt())  # get command
            if not user_command:
                continue
            # Execute function defined in cli_commands. default func print message.
            action = cli_commands.get(user_command, unknown_command)
            response = action() # Call a method defined by a command
            if action == unknown_command:
                continue
            if response:
                print(response)
            if show_raw:  # Show transferring raw str via serial port
                if _vh.read_raw:
                    print(f"--- READ RAW ---\n{_vh.read_raw}")
                if _vh.write_raw:
                    print(f"--- WROTE RAW ---\n{_vh.write_raw}")
        except EOFError:
            _do_exit()

if __name__ == '__main__':
    main()