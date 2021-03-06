# -*- coding: utf-8 -*-
"""
Created on Sun Sep 06 18:17:12 2015

@author: 70E0481
"""

import serial
import sys
import struct
import numpy as np
import threading
from queue import Queue
import glob
from time import sleep
import serial.tools.list_ports
import io


class GridEYEKit():
    def __init__(self):
        self._connected = False
        self.ser = serial.Serial()  # serial port object
        self.sio = io.TextIOWrapper(io.BufferedRWPair(
            self.ser, self.ser, 1), encoding='charmap', newline='\r\n', line_buffering=True, errors='ignore')
        self.tarr_queue = Queue(1)
        self.thermistor_queue = Queue(1)
        self.multiplier_tarr = 0.25
        # the value here in  original code is 0.0125, but I think it is wrong. Reference:ADI8000C53.pdf
        self.multiplier_th = 0.0125
        self._error = 0
       # if not self.connect():
       #     print "please connect Eval Kit"
        t = threading.Thread(target=self._connected_thread).start()

    def connect(self):
        """trys to open ports and look for valid data
        returns: true - connection good
        returns: False - not found / unsupported plattform
        """
        if self.ser.isOpen():
            self.ser.close()
        else:
            ports_available = list(serial.tools.list_ports.comports())
            if len(ports_available) <= 0:
                self._connected = False
                return False

            """try if kit is connected to com port"""
            for port in ports_available:
                print("Try to open " + port[0])
                # COM Port error is handled in list serial ports
                self.ser = serial.Serial(
                    port=port[0], baudrate=57600, timeout=0.5)
                self.sio = io.TextIOWrapper(io.BufferedRWPair(
                    self.ser, self.ser, 1), encoding='charmap', newline='\r\n', line_buffering=True, errors='ignore')
                # if 3 bytes identifyer found
                if self.serial_readline(bytes_timeout=20):
                    self._connected = True
                    return True  # GridEye found
                self.ser.close()
            self._connected = False
            return False

    # def _list_serial_ports(self):
    #     """ This function is taken from Stackoverflow and will list all serial ports"""
    #     """Lists serial ports

    #     :raises EnvironmentError:
    #         On unsupported or unknown platforms
    #     :returns:
    #         A list of available serial ports
    #     """
    #     if sys.platform.startswith('win'):
    #         ports = ['COM' + str(i + 1) for i in range(256)]

    #     elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
    #         # this is to exclude your current terminal "/dev/tty"
    #         ports = glob.glob('/dev/tty[A-Za-z]*')

    #     elif sys.platform.startswith('darwin'):
    #         ports = glob.glob('/dev/tty.*')

    #     else:
    #         raise EnvironmentError('Unsuppteorted platform')

    #     result = []
    #     for port in ports:
    #         try:
    #             s = serial.Serial(port)
    #             s.close()
    #             result.append(port)
    #         except (OSError, serial.SerialException):
    #             pass
    #     return result

    def _get_GridEye_data(self):
        """ get grid Eye data fron serial port and convert it to numpy array - also for further calculations"""
        tarr = np.zeros((8, 8))
        thermistor = 0
        data = self.serial_readline()  # read grideye value
        if len(data) >= 132:
            self._error = 0
            # Grid-Eye uses 12 bit signed data for calculating thermistor
            if not data[1] & 0b00001000 == 0:
                data[1] &= 0b00000111
                thermistor = - \
                    struct.unpack('<h', data[0:2])[0] * self.multiplier_th
            else:
                thermistor = struct.unpack('<h', data[0:2])[
                    0] * self.multiplier_th
            r = 0
            c = 0
            for i in range(2, 130, 2):  # 2,130
                # convert data to array
                # Grid-Eye uses 12 bit two's complement for calculating data
                if not data[i + 1] & 0b00001000 == 0:
                    # if 12 bit complement, set bits 12 to 16 to convert to 16 bit two's complement
                    data[i + 1] |= 0b11111000
                # combine hign and low byte to short int and calculate temperature
                tarr[r][c] = struct.unpack(
                    '<h', data[i:i + 2])[0] * self.multiplier_tarr
                c = c + 1
                if c == 8:
                    r = r + 1
                    c = 0
        else:
            self._error = self._error + 1
            print("Serial Fehler")
        """ Flip Image L-R or U-D"""""
        # tarr = np.fliplr(tarr)
        # tarr = np.flipud(tarr)
        return thermistor, tarr

    def _connected_thread(self):
        """" Background task reads Serial port and puts one value to queue"""
        while True:
            if self._connected == True:
                data = self._get_GridEye_data()
                if self.tarr_queue.full():
                    self.tarr_queue.get()
                    self.tarr_queue.put(data[1])
                else:
                    self.tarr_queue.put(data[1])

                if self.thermistor_queue.full():
                    self.thermistor_queue.get()
                    self.thermistor_queue.put(data[0])
                else:
                    self.thermistor_queue.put(data[0])

                if self._error > 5:
                    try:
                        self.ser.close()
                    except:
                        pass
                    self._connected = False
                    self._error = 0

    def get_thermistor(self):
        try:
            return self.thermistor_queue.get(True, 1)
        except:
            sleep(0.1)
            return 0

    def get_temperatures(self):
        try:
            return self.tarr_queue.get(True, 1)
        except:
            sleep(0.1)
            return np.zeros((8, 8))

    def get_raw(self):
        try:
            return self.serial_readline()
        except:
            sleep(0.1)
            return np.zeros((8, 8))

    def close(self):
        self._connected = False
        try:
            self.ser.close()
        except:
            pass

    def serial_readline(self, eol='***', bytes_timeout=20):
        """ in python 2.7 serial.readline is not able to handle special EOL strings - own implementation
        Returns byte array if EOL found in a message of max timeout_bytes byte
        Returns empty array with len 0 if not"""
        length = len(eol)
        line = bytearray()
        lineNum = 0

        while True:
            lineString = self.sio.readline()
            if (len(lineString) == 135) and (lineString[:length] == eol):
                line = bytearray(
                    lineString, encoding='charmap', errors='ignore')
                break
            else:
                lineNum += 1
                if(lineNum > bytes_timeout):
                    break

        return line[3:]
