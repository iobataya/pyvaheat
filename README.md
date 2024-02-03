# VAHEAT USB Serial Controller Wrapper

A Python wrapper class for easy communication with VAHEAT via a serial controller.

## Installation

You can install this module using `pip`:

```bash
pip install pyvaheat
```

# Usage

##1. Import the `Vaheat` class
```python
from pyvaheat import Vaheat
```

##2. Initialize an instance of the class with the appropriate serial port and baud rate.
If no serial port is specified, this class will use the port of the first device found.

```python
# Instantiate
vh = Vaheat()
```

##3. Connect to VAHEAT.
```python
vh.connect()
```

##4. Send commands by method of the class
```python
# get_info
print(vh.get_info())

# start_heating
vh.start_heating(mode='AUTO', temperature=40)
```
##5. Disconnet from the USB device when done:
```python
vh.disconnect()
```

# Example

# License
This project is licensed under the MIT License - see the LICENSE file for details.
