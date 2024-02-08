import json
import logging
import serial
from serial.tools import list_ports
import signal
import sys
import time
from typing import List, Dict

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
        "start_streaming":"once or continuous",
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

    def connect(self) -> bool:
        """Open the serial connection."""
        if self.port is None:
            devices = Vaheat.find_ports()
            if len(devices) == 0:
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
        self.info = self._get('get_info')['data']
        return self.info

    def get_status(self) -> dict:
        """The get_status command will repoly with information about the status of your device."""
        return self._get('get_status')['data']

    def get_settings(self) -> dict:
        """The get_settings command will repoly with the settings stored on your device."""
        return self._get('get_settings')['data']
    
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
        response['data']['rate'] = int(response['data']['rate'])  # type(rate) should be int
        return response['data']

    def get_profile(self, config) -> dict:
        """
        The get_profile command will reply with the requested profile or profile step
        as stored on your device.

        Args:
            config (dict): dict of parameters
        
        Note:
            keys and paramters
            profile_number (int): Number of profile
            step (int, optional): Number of step
        """
        if len(config) == 0:
            return None
        cmd = self._json_str('get_profile', data=config)
        self.write(cmd)
        response = self._json2dict(self.read_all_lines())
        if self._is_success(response):
            return response
        return None

    def start_heating(self, config) -> dict:
        """
        The 'star_heating' command allows you to change the operating mode
        of the device and start the heating process.

        Args:
            config (dict): dict of parameters
        
        Note:
            keys and parameters
            mode                     (str): Device mode. (AUTO/DIRECT/SHOCK/PROFILE)
            power        (float, optional): Relative power (%) in DIRECT and SHOCK mode. Defaults 0.1%
            temperature  (float, optional):Temperature setoing in AUTO mode. Defaults 25 degC.
            duration     (float, optional): Shock duration in SHOCK mode [0.1-9999]
            profile_number (int, optional): Profile selection [1-9] in PROFILE mode. Defaults -1
        """
        if len(config) == 0:
            return None
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
                    raise ValueError("Profile number should be 1-9.")
                d['profile_number'] = profile_number
            if 'ignore_limit_error':
                d['ignore_limit_error'] = config['ignore_limit_error']
        else:
            raise ValueError(f"Mode {mode} is not allowed.")
        self.write(self._json_str('start_heating',data=d))

        response = self._json2dict(self.read_all_lines())
        if self._is_success(response):
            logging.info(f"Heating started by {mode} mode.")
            return response
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
        if mode == 'continuous' or mode == 'once':
            conf = self.get_streaming()
            conf['mode'] = mode
            return self.set_streaming(conf)
        else:
            return False

    def stop_streaming(self) -> bool:
        """
        Stop streaming
        """
        self.serial.reset_input_buffer()
        conf = self.get_streaming()
        conf['mode'] = 'off'
        return self.set_streaming(conf)

    def do_reset(self, config) -> None:
        """
        do_reset command allows you to reset parts of your device.
        
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
        if len(config) == 0:
            return False
        cmd = self._command_str('set_settings', data=config)
        self.write(cmd)
        self._is_success(self._json2dict(self.read_all_lines()))
        return True

    def set_streaming(self, config):
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
        if len(config)==0:
            return False
        cmd = self._json_str('set_streaming', data=config)
        self.write(cmd)
        self._is_success(self._json2dict(self.read_all_lines()))
        return True

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
        return self._is_success(self._json2dict(self.read_all_lines()))

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
        if len(profile) == 0:
            return None
        self.write(self._json_str('set_profile',profile))
        return self._is_success(self._json2dict(self.read_all_lines()))

    def _json2dict(self, json_str:str) -> dict:
        """Try to convert from JSON str to dict"""
        try:
            d = json.loads(json_str)
            return d
        except json.JSONDecodeError as e:
            logging.info(f"JSON decoding error: {e.msg} at {e.pos}\nInput data: {e.doc}")
            raise ValueError(e.msg)

    def read(self) -> str:
        """
        Read a JSON line from the serial port buffer.

        Returns:
            str: Returned JSON line
        """
        if self.serial and self.serial.is_open:
            try:
                json_str = self.serial.readline().decode('utf-8').rstrip()
                logging.debug(f"Read:\n{json_str}")
                return json_str
            except Exception as e:
                print(f"Error reading data: {e}")
        logging.debug("Nothing read.")
        return ""

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
                logging.debug(f"Read:\n{json_str}")
                self.read_raw = json_str
                return json_str
            except Exception as e:
                logging.error(f"Error reading all lines: {e}")
        logging.debug("Nothing read.")
        return ""

    def write(self, json_str) -> None:
        """
        Write JSON string to the serial port.

        Args:
            data (str): JSON string to write
        """
        if self.serial and self.serial.is_open:
            self.write_raw = json_str
            try:
                self.serial.write(json_str.encode())
                logging.debug(f"Wrote:\n{json_str}")
            except Exception as e:
                print(f"Error writing data: {e}")

    def _get(self, cmd) -> dict:
        """
        Get response after writing cmd

        Args:
            cmd(str): string of command
        """
        if self.serial and self.serial.is_open:
            self.write(self._json_str(cmd))  # Write get_XXX without data
            data = self._json2dict(self.read_all_lines())  # Read data in buffer as dict
            return data
        else:
            msg = "Connection is not open."
            logging.error(msg)
            raise OSError(msg)

    def _is_success(self, d:dict) -> bool:
        """
        Check the previous command was accepted successfully.

        Args:
            response (dict): Response dict from device

        Returns:
            bool: Success
        """
        if 'success' in d and ['success'] == False:
            return False
        if 'error' in d:
            print(d)
            msg = f"Error: {d['error']}, Code:{d['code']}, Parent:{d['parent']} at {d['at']}"
            logging.error(msg)
            raise OSError(msg)
        return True

    def _json_str(self, cmd:str, data=None) -> str:
        """
        Returns encoded str to send

        Args:
            cmd             (str): Command to send. It should be in allowed API_CMD
            data (dict, optional): Parameters dict. Defaults to None sending 'true' as value

        Returns:
            str: Encoded JSON string

        Raises:
            ValueError: Command is not allowed
        """
        if cmd not in self.API_CMD:
            m = f'{cmd} is not in allowed commands.'
            logging.error(m)
            raise ValueError(m)
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
        lines = json_string.split('\n')
        corrected_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Check if the line ends with an opening or closing brace, or contains "data:":
            if stripped_line and not stripped_line.endswith('{') and not stripped_line.endswith('}') and not stripped_line.endswith('":'):
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
        print(f"Parameters: ({msg})")
        s = input("JSON: ")
        if len(s)==0:
            return {}
        data = _vh._json2dict(s)
        str_json = json.dumps(data)
        if len(data) > 0:
            print(f"Sending paremeter is : {str_json}")
            return data
    except EOFError:
        _do_exit()
    return {}

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
    return _vh.start_streaming(_input_params(msg="mode (once/continuous)"))

def set_keylock() -> bool:
    """set_keylock by CLI"""
    s = input(prompt(input_type=Vaheat.API_CMD['set_keylock']))
    if s.lower() == "true":
        return _vh.set_keylock(True)
    elif s.lower() == "false":
        return _vh.set_keylock(False)

def get_profile() -> bool:
    num = input("Enter profile_number (1-9): ")
    config = {}
    if 1 <= int(num) and int(num) <= 9:
        config['profile_number'] = int(num)
        print("Enter step (1-20) or 0 for without specify.")
        step = input("Step (1-20): ")
        if 1 <= int(step) and int(step) <=20:
            config['step'] = int(step)
        _vh.get_profile(config)
        # TODO: get_profile再考、テスト　(;ﾟ∀ﾟ)=3ﾊｧﾊｧ
    return False

def set_settings() -> bool:
    """set_settings by CLI"""
    return _vh.set_streaming(_input_params(msg=Vaheat.API_CMD["set_settings"]))

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
    config = _input_params()
    return _vh.do_reset(config)

def read() -> str:
    """Read raw line from buffer"""
    return _vh.read()

def read_all() -> str:
    """Read all raw lines from buffer"""
    return _vh.read_all_lines()

def write() -> str:
    """Write raw line to device"""
    s = input("Enter JSON str to write: ")
    return _vh.write(s)

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
        "read": read,
        "read_all": read_all,
        "write": write,
        "exit": _do_exit,
    }

    while True:
        try:
            user_command = input(prompt())  # get command
            if user_command=='':
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