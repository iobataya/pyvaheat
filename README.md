# VAHEAT USB Serial Controller Wrapper
A Python wrapper class of serial controller and interactive CLI for VAHEAT controller

# Download
  * Download a script '**pyvaheat.py**'. (Not uploaded to pypi yet.)
  * Install pyserial module by ```pip install pyserial``` if not installed yet.

# Usage of CLI
Run pyvaheat.py. Prompt ask commands for API like 'connect', 'start_heating' and 'get_info'.  First of all, connect to device. If serial port is not specified, program will detect connected VAHEAT automatically. See also an wiki page for an example.
```
>connect
```
After establishing connection, prompt should show a serial number of your device. When a command needs parameters, prompt will ask parameters formatted as JSON. Try inputting API commands in user manual of VAHEAT. 
```
>get_info
>get_status
>start_heating
>  {"mode":"auto","temperature":45}
>stop_heating
>exit
```

# Usage of class
Your python script can use VAHEAT device by importing Vaheat class. See also an wiki page.

## 1. Import the Vaheat class
```python
from pyvaheat import Vaheat
```
## 2. Initialize and connect
If no serial port is specified, this class will use the port of the first device found.

```python
# Instantiate
vh = Vaheat()
vh.connect()
```
## 3. Send commands by method of the class
```python
# get_info
print(vh.get_info())

# start_heating
vh.start_heating(mode='AUTO', temperature=40)
```
## 4. Disconnet from the USB device when done:
```python
vh.disconnect()
```
# License
This project is licensed under the MIT License - see the LICENSE file for details.
