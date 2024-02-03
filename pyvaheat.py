import serial
from serial.tools import list_ports
import time
import json
import logging

# Set up logging
# logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

class Vaheat:
    """
    Wrapper class of serial communication to VAHEAT

    Attributes:
        port       (str): Port to connect VAHEAT
        info      (dict): Device info
        baud_rate  (int): Baud rate for serial communication. maximum: 921600
        timeout    (int): Read timeout in seconds.
        serial  (Serial): Serial object
        keylock   (bool): Whether a device is keylocked
        MODES     (list): List of str for modes to send
        COMMANDS  (list): List of str for commands to send
    """
    AUTO = 'auto'
    DIRECT = 'direct'
    SHOCK = 'shock'
    PROFILE = 'profile'
    COMMANDS = ["get_info",     "get_status",   "get_settings","get_streaming","get_profile",
                "start_heating","stop_heating", "do_reset",    "set_keylock",
                "set_settings", "set_streaming","set_mode",    "set_profile"]

    def __init__(self, port=None, baud_rate=9600, timeout=0.5):
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
        if port is None:
            self.port = self._find_vaheat()
        else:
            self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.serial = None

    def connect(self):
        """Open the serial connection."""
        try:
            self.serial = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
            logging.info(f"Connected to {self.port}")

        except serial.SerialException as e:
            logging.error(f"Error opening serial port {self.port}: {e}")

    def disconnect(self):
        """Close the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            self.serial.close()
            logging.info(f"Disconnected from {self.port}")

    def get_info(self) -> dict:
        """The get_info command will reply with information about your device."""
        return self._get(0)

    def get_status(self) -> dict:
        """The get_status command will repoly with information about the status of your device."""
        return self._get(1)

    def get_settings(self) -> dict:
        """The get_settings command will repoly with the settings stored on your device."""
        response = self._get(2)
        return response['data']

    def get_streaming(self) -> dict:
        """
        The get streaming command will reply with the streaming settings stored on your device.
        Since current VAHEAT device returns wrong JSON format missing comma, raw string is manupilated.
        """
        self.write(self._command_str(cmd_idx=3))
        raw_str = self.read_all_lines()

        # Manipulate raw string
        corrected = self._add_commas(raw_str)

        response =self._response_to_dict(corrected)
        return response['data']

    def get_profile(self) -> dict:
        """
        The get_profile command will reply with the requested profile or profile step
        as stored on your device. To select, which profile or profile step you want,
        set_profile values.
        """
        return self._get(4)

    def start_heating(self, mode='AUTO',power=None, temperature=None, duration=None,
                     profile_number=None, ignore_limit_error=None) -> None:
        """
        The 'star_heating' command allows you to change the operating mode
        of the device and start the heating process.

        Args:
            mode                     (str): Device mode. (AUTO/DIRECT/SHOCK/PROFILE)
            power        (float, optional): Relative power (%) in DIRECT and SHOCK mode. Defaults 0.1%
            temperature  (float, optional):Temperature setoing in AUTO mode. Defaults 25 degC.
            duration     (float, optional): Shock duration in SHOCK mode [0.1-9999]
            profile_number (int, optional): Profile selection [1-9] in PROFILE mode. Defaults -1
        """
        d = {'mode':mode}
        if mode.lower() == self.AUTO:
            if temperature:
                d['temperature'] = temperature
        elif mode.lower() == self.DIRECT:
            if power:
                d['power'] = power
        elif mode.lower() == self.SHOCK:
            if power:
                d['power'] = power
            if duration:
                d['duration'] = duration
        elif mode.lower() == self.PROFILE:
            if profile_number:
                if profile_number < 1 or profile_number > 9:
                    raise ValueError("Profile number should be 1-9.")
                d['profile_number'] = profile_number
            if ignore_limit_error:
                d['ignore_limit_error'] = ignore_limit_error
        else:
            raise ValueError(f"Mode {mode} is not allowed.")
        self.write(self._command_str(val=d, cmd_idx=5))
        self._check_success(self.read_all_lines())
        logging.info(f"Heating started by {mode} mode.")

    def stop_heating(self) -> None:
        """ The stop_heating command allows you to stop the heating process immediately."""
        self._check_success(self._get(6))
        logging.info("Heating stopped.")

    def start_streaming(self, mode:str='continuous') -> None:
        """
        Start streaming with current streaming settings.
        Only 'continuous'(default) or 'once' mode is accepted.

        Args:
            mode (str, optional):continuous or once
        """
        if mode == 'continuous' or 'once':
            conf = self.get_streaming()
            conf['mode'] = mode
            self.set_streaming(conf)

    def stop_streaming(self) -> None:
        """
        Stop streaming
        """
        self.serial.reset_input_buffer()
        conf = self.get_streaming()
        conf['mode'] = 'off'
        self.set_streaming(conf)

    def do_reset(self, everything=False, profiles=False, settings=False,pid=False,profile_number=-1) -> None:
        d = {
            'all':everything,
            'profiles':profiles,
            'settings':settings,
            'pid':pid,}
        if profile_number >= 1 and profile_number <= 9:
            d['profile_number'] = profile_number
        self.write(self._command_str(val=d, cmd_idx=7))
        self._check_success(self.read_all_lines())
        logging.info(f"Reset executed. {d}")

    def set_keylock(self, keylock=True):
        cmd = self._command_str(val=keylock, cmd_idx=8)
        self.write(cmd)
        self._check_success(self.read_all_lines())
        if keylock:
            logging.info(f"Device is keylocked.")
        else:
            logging.info(f"Device is key-unlocked.")
        self.keylock = keylock

    def set_settings(self, settings_dict) -> bool:
        """
        Set settings defined by dictionary on your device. (See manual 6.3.3)
        The dictionary is avaiable get_settings()

        Args:
            settings_dict (dict): {brightness,haptic_strength,temperature_limit,
                                  limit_enabled, pid{p,i,d}
        """
        cmd = self._command_str(val=settings_dict, cmd_idx=9)
        self.write(cmd)
        self._check_success(self.read_all_lines())
        return True

    def set_streaming(self, settings_dict):
        """
        set_streaming command allows you to change the streaming settings stored on your device.
        The dictionary is avaiable get_settings()

        Args:
            settings_dict (dict): {mode, rate, time, remaining, onoff, temperature,
                                    setpoint, power, profile_step, resistance}
        """
        cmd = self._command_str(val=settings_dict, cmd_idx=10)
        self.write(cmd)
        self._check_success(self.read_all_lines())
        return True

    def set_mode(self, mode, power=None, temperature=None, duration=None, profile_number=None) -> bool:
        d = {'mode':mode}
        if mode.lower() == Vaheat.AUTO:
            if temperature:
                d['temperature'] = temperature
        elif mode.lower() == Vaheat.DIRECT:
            if power:
                d['power'] = power
        elif mode.lower() == Vaheat.SHOCK:
            if power:
                d['power'] = power
            if duration:
                d['duration'] = duration
        elif mode.lower() == Vaheat.PROFILE:
            if profile_number:
                if profile_number < 1 or profile_number > 9:
                    raise ValueError("Profile number should be 1-9.")
                d['profile_number'] = profile_number
        else:
            raise ValueError(f"Mode {mode} is not allowed.")
        self.write(self._command_str(val=d, cmd_idx=11))  # 11: set_mode
        self._check_success(self.read_all_lines())
        logging.info(f"{mode} mode is selected.")
        return True

    def set_profile(self, profile_number, name, steps) -> bool:
        d = {'profile_number':profile_number, 'name':name, 'steps':steps}
        self.write(self._command_str(val=d, cmd_idx=12))  # 12: set_profile
        self._check_success(self.read_all_lines())
        return True

    def read(self) -> str:
        """
        Read data from the serial port.

        Returns:
            dict: Returned data as dict
        """
        if self.serial and self.serial.is_open:
            try:
                response = self.serial.readline().decode('utf-8').rstrip()
                return response
            except Exception as e:
                print(f"Error reading data: {e}")
        return ""

    def read_all_lines(self) -> str:
        if self.serial and self.serial.is_open:
            try:
                lines = ''
                while True:
                    l = self.serial.readline().decode('utf-8')
                    if not l:
                        break  # No more data, exit loop
                    lines += l
                return lines.rstrip()
            except Exception as e:
                logging.error(f"Error reading all lines: {e}")
        return ""

    def write(self, data):
        """
        Write data to the serial port.

        Args:
            data (str): String to write
        """
        if self.serial and self.serial.is_open:
            try:
                self.serial.write(data.encode())
            except Exception as e:
                print(f"Error writing data: {e}")

    def _get(self, cmd_idx:int) -> dict:
        """
        Get response after writing COMMAND[cmd_idx]

        Args:
            index of COMMAND
        """
        if self.serial and self.serial.is_open:
            self.write(self._command_str(cmd_idx=cmd_idx))  # Write get_XXX
            data = self._response_to_dict(self.read_all_lines())  # Read data in buffer as dict
            return data
        else:
            msg = "Connection is not open."
            logging.error(msg)
            raise OSError(msg)

    def _check_success(self, d:dict) -> bool:
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
            msg = f"Error: {d['error']}, Code:{d['code']}, Parent:{d['parent']} at {d['at']}"
            logging.error(msg)
            raise OSError(msg)
        return True

    def _response_to_dict(self, decoded_line:str) -> dict:
        """ Returns dict from decoded JSON line"""
        return json.loads(decoded_line)

    def _command_str(self, cmd:str='', val:dict=None, cmd_idx:int=-1) -> str:
        """
        Returns encoded str to send

        Args:
            cmd     (str, optional): Command to send. It should be in allowed COMMANDS
            val    (dict, optional): Value dict. Defaults to None sending 'true' as value
            cmd_idx (int, optional): Index of COMMANDS to send.

        Returns:
            str: Encoded string

        Raises:
            ValueError: Command is allowed
        """
        if cmd_idx>=0:
            cmd = self.COMMANDS[cmd_idx]
        else:
            if cmd not in self.COMMANDS:
                m = f'{cmd} is not in allowed commands.'
                logging.error(m)
                raise ValueError(m)
        if val == None:
            val = True
        data = json.dumps({cmd:val})
        return data

    def _find_vaheat(self):
        """ Returns serial port of VAHEAT as str """
        ports = serial.tools.list_ports.comports()
        for port, desc, hwid in sorted(ports):
            if "VID:PID=0483:5740" in hwid: # vendor ID and product ID of VAHEAT
                logging.info(f"VAHEAT found at {port}.")
                return port
        logging.error(f"Failed to find VAHEAT device.")
        raise OSError("Failed to find VAHEAT device.")

    def __del__(self):
        """
        Destructor to ensure the serial connection is closed.
        """
        self.disconnect()

    def _add_commas(self, json_string):
        """
        Current VAHEAT device respond irregular JSON format missing commas by 'get_streaming' command
        {
          "command": "GET_STREAMING",
          "success": true,
          "data":
          {
            "mode": "off"
            "rate": "1"    # < should be int, but response is str
            "time": false
            "remaining": false
            "onoff": false
            "temperature": false
            "setpoint": false
            "power": false
            "profile_step": false
            "resistance": false
          }
        }
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
        return self.remove_last_comma(corrected_json_string)
    def remove_last_comma(self,s):
        # Reverse the string
        reversed_s = s[::-1]
        # Replace the first (actually last) comma found
        corrected_s = reversed_s.replace(',', '', 1)
        # Reverse the string back to original order
        return corrected_s[::-1]

    def __str__(self):
        if self.serial.is_open:
            return 'VAHEAT ({self.port}, connected)'
        else:
            return 'VAHEAT ({self.port}, not connected)'
