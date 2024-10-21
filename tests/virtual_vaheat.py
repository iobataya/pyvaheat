import serial
import serial.tools.list_ports
import time

# Define the name of the virtual serial port
virtual_port_name = 'COM99'

try:
    # Create a virtual serial port using pyserial
    virtual_serial_port = serial.Serial(virtual_port_name, baudrate=9600)
    print(f"Virtual serial port '{virtual_port_name}' created successfully.")

    while True:
        # Read data from the sender
        received_data = virtual_serial_port.read(20)  # Read up to 20 bytes

        if received_data:
            # Process received data
            received_str = received_data.decode('utf-8')
            print(f"Received data: {received_str}")

            # Respond to the sender by adding "!" to the received data
            response_str = received_str + "!"
            virtual_serial_port.write(response_str.encode('utf-8'))
            print(f"Response sent: {response_str}")

        # Wait for 2 seconds (0.5Hz listening frequency)
        time.sleep(2)

except serial.SerialException as e:
    print(f"Error creating virtual serial port: {e}")

finally:
    # Close the virtual serial port when done
    if virtual_serial_port.is_open:
        virtual_serial_port.close()
        print("Virtual serial port closed.")
