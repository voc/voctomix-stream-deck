#!/usr/bin/env python

import sys
import os
import numpy as np

import hid
from PIL import Image, ImageDraw, ImageFont

HID_VENDOR = 4057
HID_PRODUCT = 96

NUM_KEYS = 15
NUM_ROWS = 3
NUM_KEYS_ROW = 5
ICON_SIZE = 72, 72

NUM_TOTAL_PIXELS = ICON_SIZE[0]*ICON_SIZE[1]
NUM_PAGE1_PIXELS = 2583
NUM_PAGE2_PIXELS = NUM_TOTAL_PIXELS-NUM_PAGE1_PIXELS

RESET_DATA = [11, 99, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
BRIGHTNESS_DATA = [5, 85, 170, 209, 1, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

HEADER_PAGE1 = [2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 66, 77, 246,
                60, 0, 0, 0, 0, 0, 0, 54, 0, 0, 0, 40, 0, 0, 0, 72, 0, 0, 0,
                72, 0, 0, 0, 1, 0, 24, 0, 0, 0, 0, 0, 192, 60, 0, 0, 196, 14,
                0, 0, 196, 14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

HEADER_PAGE2 = [2, 1, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def hex2rgb(col):
    """
    Convert from hex color string to RGB tuple.

    Parameters
    ----------
    col : Hex color string for background.

    Returns
    ----------
    color : RGB tuple (0-255,0-255,0-255)
    """
    if isinstance(col, tuple):
        # assume this is RGB in (0-1) format
        # not an intended input, but we can work with it
        rgb = tuple(np.array(col)*255)
        return rgb

    # if preceded by a '#', remove it
    col = col.replace('#', '')

    rgb = tuple(bytes.fromhex(col))
    return rgb

class StreamDeck(object):
    """
    StreamDeck:
    A Framework for Using the Elgato Stream Deck
    for Experimental Psychology Research
    """

    class Icon(object):
        """
        Object for preparing icons for ElGateau.
        """

        ########################################
        #
        # Icon generation functions
        #
        # hex2rgb, solid, prep, text
        #
        ########################################

        def solid(col='000000'):
            """
            Create a icon that is a solid color.

            Parameters
            ----------
            col : Hex color string for background.

            Returns
            ----------
            icon : Icon object (from Icon class)
            """
            # make blank image of a solid color
            rgb = hex2rgb(col)
            ico = Image.new('RGBA', ICON_SIZE, rgb+(255,))

            icon = {}
            icon['ico'] = ico
            icon['label'] = 'solid'
            icon['contents'] = col
            return icon

        def prep(filename, pad=0):
            """
            Prepare icon (read from file, pad, resize).

            Parameters
            ----------
            filename : Filename for icon to prepare,
                       needs to be a PNG in the "icons" folder.
            bright : px
                Pad the icon before resizing, this way the icon
                doesn't go right to edge of display.

            Returns
            ----------
            icon : Icon object (from Icon class)
            """
            # read icon
            ico = Image.open(os.path.join("icons", filename+".png"))

            if pad != 0:
                # pad with blank space if don't know
                padded_size = ico.size[0]+pad, ico.size[1]+pad
                padded_im = Image.new("RGBA", padded_size)
                padded_im.paste(ico, (int((padded_size[0]-ico.size[0])/2),
                                      int((padded_size[1]-ico.size[1])/2)))
                ico = padded_im

            # ensure final image is 72x72
            ico.thumbnail(ICON_SIZE)

            icon = {}
            icon['ico'] = ico
            icon['label'] = 'image'
            icon['contents'] = filename
            return icon

        def text(text, ico=None, col='ffffff', back='000000',
                 font='VeraMono-Bold', size=14, position=(31, 31)):
            """
            Overlay text over icon.

            Parameters
            ----------
            text : str
                Text to write.
            ico : 72x72 RGBA image
                Should have been output from icon_prep or icon_solid.
                Optional, defaults to black background.
            col : Hex color code string for text.
                Optional, defaults to white ('ffffff').
            back : Hex color string for background.
                Optional, defaults to black ('000000').
            font : Font filename, should be in "fonts" folder.
                Optional, defaults to VeraMono-Bold.
            size : Font size.
                Optional, defaults to 14.
            position : (int, int), Center of where to draw the text

            Returns
            ----------
            icon : Icon object (from Icon class)
            """
            # make a solid color background if necessary
            if back != '000000':
                ico = StreamDeck.Icon.solid(back)
            elif ico is None:
                ico = StreamDeck.Icon.key_blank

            # underlay
            base = ico['ico']

            # make a blank image for the text,
            # initialized to transparent text color
            txt = Image.new('RGBA', base.size, (255, 255, 255, 0))

            # setup font
            fnt = ImageFont.truetype(os.path.join("fonts", font+".ttf"), size)
            rgb = hex2rgb(col)
            # get a drawing context
            draw = ImageDraw.Draw(txt)

            # write text
            width, height = draw.textsize(text, font=fnt)
            position = (position[0]-width/2+4, position[1]-height/2+4)
            # convert location positions to int (rather than float)
            position = tuple(map(int, position))

            draw.text(position, text, font=fnt, fill=rgb+(255,), align='center')

            # flatten background and text
            ico = Image.alpha_composite(base, txt)

            icon = {}
            icon['ico'] = ico
            icon['label'] = 'text'
            icon['contents'] = text
            return icon

        # pre-generate a blank key for later functions
        key_blank = solid()
        key_blank['label'] = '_'
        key_blank['contents'] = '_'

    # functions

    ########################################
    #
    # Basic device interaction functions
    #
    # open, reset, set_brightness, key_remap
    #
    ########################################

    def __init__(self, dev_mode=False):
        """
        Open initial connection to Elgato Stream Deck device
        and sets up initial variables.
        """
        # preload the blank key
        self.key_blank = self.Icon().key_blank

        # initiate internal representation
        self.display_status = {}
        self.display_status['label'] = {}
        self.display_status['contents'] = {}
        self.display_status['ico'] = {}
        for k in range(1, NUM_KEYS+1):
            self.display_status['label'][k] = '_'
            self.display_status['contents'][k] = '_'
            # for now use 'blank' to init easier,
            # but really should be a solid()
            self.display_status['ico'][k] = '_'

        # try to connect to device
        try:
            self.device = hid.device(HID_VENDOR, HID_PRODUCT)
            self.device.open(HID_VENDOR, HID_PRODUCT)
        except:
            print("No device found.")
            sys.exit(0)
        # send a reset command,
        # otherwise display may have icons from a previous instance
        self.reset()

    def __enter__(self):
        return self

    def __exit__(self):
        """
        Close connection to Elgato Stream Deck device.
        """
        self.device.close()

    def reset(self):
        """
        Send reset command.
        """
        self.device.send_feature_report(RESET_DATA)

    def set_brightness(self, bright):
        """
        Set brightness of displays.

        Parameters
        ----------
        bright : int, 0-100
            Brightness value to set LCD display to.
        """
        BRIGHTNESS_DATA[5] = bright
        self.device.send_feature_report(BRIGHTNESS_DATA)

    def key_remap(self, key):
        """
        Remaps key numbers.

        Parameters
        ----------
        key : int, key number on device (1-15)
        (5,4,3,2,1,10,9,8,7,6,15,14,13,12,11)
        OR
        (int,int) for (row,column) notation (1-3,1-5)

        Returns
        ----------
        key : int, key number on device (1-15)
        (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15)
        """
        if isinstance(key, int):
            # simple remap of left-right ordering
            key = (np.floor((key-1)/NUM_KEYS_ROW))*NUM_KEYS_ROW + \
                    (NUM_KEYS_ROW-(np.mod(key-1, NUM_KEYS_ROW)))
        elif isinstance(key, tuple):
            # (r,c) notation
            key = (key[0]-1)*NUM_KEYS_ROW + key[1]
            key = self.key_remap(key)  # still need to re-map ordering
        return int(key)

    ########################################
    #
    # Key display functions
    #
    # display_icon, display_clear
    #
    ########################################

    def display_icon(self, key, icon, remap=True):
        """
        Low-level function not intended to be called directly.
        (Does not update display_status, use display_update instead.)

        Pushes an icon to a key display on the device.

        Parameters
        ----------
        key : int, Key number on device (1-15)
        OR key: tuple, Key number in row,column notation (1-3,1-5)
        icon : Icon object (from Icon class)
        """
        # icon gets written to display from right to left,
        # so need to mirror it before sending so it looks correct
        ico = icon['ico']
        ico = ico.transpose(Image.FLIP_LEFT_RIGHT)

        # buffer pixel data into a list and shuffle colors to BGR
        icobuffer = list(ico.getdata())  # RGBA
        pixels = np.array([])
        for pixel in range(0, NUM_TOTAL_PIXELS):
            r = icobuffer[pixel][0]
            g = icobuffer[pixel][1]
            b = icobuffer[pixel][2]
            pixels = np.concatenate([pixels, np.array([b, g, r])])

        if remap:
            # remap the key locations to make more sense
            key = self.key_remap(key)

        # send pixel data to elg
        header = HEADER_PAGE1
        header[5] = key
        msg = header + pixels[range(0,
                                    NUM_PAGE1_PIXELS*3)].astype(int).tolist()
        self.device.write(msg)

        header = HEADER_PAGE2
        header[5] = key
        msg = header + pixels[range((NUM_PAGE1_PIXELS*3),
                                    NUM_TOTAL_PIXELS*3)].astype(int).tolist()
        self.device.write(msg)

    def display_clear(self, keys, rc=False):
        """
        Clears the display for a key on the device.

        Parameters
        ----------
        keys : int, key number on device (1-15)
            OR list (e.g., (1,4,12))
            OR 'all'

        rc : boolean, Use the r,c (row,column) notation or not
            If rc=True, list of keys must be lists of tuples
            E.g., ((1,1),(1,4),(3,2))
        """
        if keys == 'all':
            # list(range) works, but is slow
            # let's be more responsive
            self.reset()
            # reset works with device
            self.display_clear(1)
            keys = list(range(1,16))
            for k in keys:
                self.display_update(k, self.key_blank, display=False)
                # we want to update display_status, but not push to device
            return

        if not rc:
            if isinstance(keys, int):
                keys = (keys,)
            for k in keys:
                self.display_update(k, self.key_blank)

        elif rc:
            # if it's a tuple in (r,c) format
            if isinstance(keys[0], int):
                keys = (keys,)
            for k in keys:
                self.display_update(k, self.key_blank)

    def display_update(self, key, icon, display=True):
        """
        Updates device key displays as well as
        internal representation of device key displays (display_status).

        Pushes icon data to the device. 

        Parameters
        ----------
        key : int, Key number on device (1-15)
        OR key: tuple, Key number in row,column notation (1-3,1-5)
        icon : Icon object (from Icon class)
        """
        # if tuple, remap
        if isinstance(key, tuple):
            key = self.key_remap(key)
            # need to remap twice to adjust for rc notation...
            key = self.key_remap(key)

        # update internal representation
        self.display_status['label'][key] = icon['label']
        self.display_status['contents'][key] = icon['contents']
        self.display_status['ico'][key] = icon['ico']

        # remap the key locations
        key = self.key_remap(key)

        # if not, will update display_status, but not actual device/display_state
        if display:
            # push to device
            self.display_icon(key, icon, remap=False)  # already remapped!

    ########################################
    #
    # Key button functions
    #
    # button_getch, button_clear,
    # button_listen_key, button_listen_count
    #
    ########################################

    def button_getch(self, remap=True, timeout=0):
        """
        Detect button presses for the keys on the device.

        Parameters
        ----------
        remap : boolean, use the remapping or not
        timeout : int, How many ms to wait for device. Optional.

        Returns
        ----------
        key : int, Key number on device (1-15)
        """
        # wait for button press
        state = self.device.read(NUM_KEYS+1)
        key = np.where(np.array(state) == 1)
        key = int(key[0][1])
        if remap:
            key = self.key_remap(key)

        # wait for release
        state = self.device.read(NUM_KEYS+1)
        if len(np.where(np.array(state) == 1)) > 1:
            # no keys currently pressed
            raise ValueError('Unexpected getch state.')

        return (key)

    def button_empty(self, timeout=5):
        """
        Device buffers button presses, so can carry over to following getch.
        Need to empty the buffer.

        Parameters
        ----------
        timeout : int, How many ms to wait for device. Optional.
        """
        state = [0]
        while len(state) > 0:
            # hid.device.read has a timeount parameter!!
            state = self.device.read(NUM_KEYS+1, timeout_ms=timeout)

    def button_listen_key(self, keys, rc=False):
        """
        Listen for specified key to be pressed.

        Parameters
        ----------
        keys : int or list of ints, Key(s) to listen for
            E.g., (1,4,12)

        rc : boolean, Use the r,c (row,column) notation or not
            If rc=True, list of keys must be lists of tuples
            E.g., ((1,1),(1,4),(3,2))

        Returns
        ----------
        button : int, Key detected (1-15)
            If rc=True, will return tuple in same format
        """
        # empty device buffer
        self.button_empty()
        # initiate button with 0, since no presses just yet
        button = 0

        # listen
        # only accepts certain key responses
        if not rc:
            if isinstance(keys, int):
                keys = (keys,)
            while button not in keys:
                button = self.button_getch()

        elif rc:
            # not implemented yet
            print('Not implemented yet')

        return (button)

    def button_listen_count(self, count):
        """
        Listen for specific number of button presses

        Parameters
        ----------
        count : Number of key presses to listen for

        Returns
        ----------
        key_list : list, keys pressed
        """
        # empty device buffer
        self.button_empty()
        # get time for starting to listen
        time_start = time.time()
        # define the counting variable
        count_i = 0
        # define the variable where we'll keep our list
        key_list = []

        # listen
        # stop after 'count' presses
        while count_i < count:
            button = self.button_getch()
            key_list.append(button)
            count_i += 1

        return (key_list)

