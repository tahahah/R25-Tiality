# Mechatronics Integration Guide

## Audio Sub-Team

# Accessing audio stream

## Common requirements

The microphone is connected to the Debian-based Raspberry Pi or Laptop (“host”) via USB 1.1 FS.

The host can determine whether the microphone has been enumerated using: `sudo lsusb -v`

The host can determine whether the sound interface (ALSA) has registered the microphone with a generic driver using: `arecord -l -L` → [expected output here](#alsa-enumeration).

## Microphone array

The STM32 (“microphone”) is connected to the host via a data-capable USB cable.

The host can determine whether the microphone has been enumerated using: `sudo lsusb -v -d cafe:` → [expected output here](#usb-enumeration).

Use the previous command to determine which soundcard and device ALSA has registered the microphone to (`-D hw:<CARD>,<DEVICE>`). The host can record the audio interface using `arecord -f S16_LE -r 48000 -c 4 -D hw:1,0 output.wav`

## Generic microphone {#generic-microphone}

Check the microphone’s user manual for supported sample rates, channels, and encoding format. Typical values are:

* Format: 32-bit float (`FLOAT_LE`), 16-bit signed PCM (`S16_LE`)  
* Rate: 44100 kHz  
* Channels: 2

# Programmatic processing of audio stream

## Prerequisites

The installed sound interface must be ALSA. This should be the case by default on Debian-based operating systems using a Linux kernel ≥ 2.6.

Other packages:

* `sudo apt install libasound2-dev libogg-dev libopus-dev libopusfile-dev libopusenc-dev libportaudio`  
* If `libopusenc-dev` isn’t available, download it from the [Debian Package Repo](https://packages.debian.org/sid/libopusenc-dev).

## Script information

Thread output: (via Queue)

* 20 ms encoded packets  
* Timestamp  
* Sequence number  
* Encoder algorithm delay in samples

CaptureObject methods:

* Start capture  
* Stop capture  
* Blocking read  
* Callback read implemented but not currently used

Design trade-offs:

* 20 ms packet length ensures Opus can get good compression without increasing latency too much  
* If the queue is full, the first packet is discarded and new packet is queued

## Using the script

1. Clone the repository ([https://github.com/ECE4191-Roverlords/Safari-Sensor-Payload](https://github.com/ECE4191-Roverlords/Safari-Sensor-Payload), subdirectory `odette/ALSA_Capture_Stream`) or download the release package ([ALSA\_Capture\_Stream.zip](https://drive.google.com/file/d/1FG3rnyWDXroJSuczBhzJdt7cHaLnIF_u/view?usp=sharing)).  
2. `cd` into the directory.  
3. Create a virtual environment with `python3 -m venv .venv`  
4. Load the virtual environment with `source .venv/bin/activate`  
5. Install required packages with `pip3 install -r requirements.txt`  
6. Run the script with `python3 main.py -c 4 -e 1 -d 1,0`

Note: You may need to change the `-d`evice option depending on how the Raspberry Pi mounts the microphone (see: [Generic microphone](#generic-microphone)). You will also need to change the `-c`aptured channels option to 1 or 2 if not using the four-channel microphone.

Script options:

`usage: PiAudioThread [-h] [-d DEVICE] [-c {1,2,4}] [-e {1,2}]`

`Captures and encodes audio packets from the supplied ALSA device.`

`options:`  
  `-h, --help            show this help message and exit`  
  `-d DEVICE, --device DEVICE`  
                        `` ALSA device to use, specified as <card>,<device>, e.g., `1,0` ``  
  `-c {1,2,4}, --capch {1,2,4}`  
                        `Number of channels to capture`  
  `-e {1,2}, --encch {1,2}`  
                        `Number of channels to encode`

# Expected outputs

## USB enumeration {#usb-enumeration}

`sudo lsusb -v -d cafe:`

`Bus 003 Device 084: ID cafe:4010 PaniRCorp MicNode_4_Ch`  
`Device Descriptor:`  
  `bLength                18`  
  `bDescriptorType         1`  
  `bcdUSB               2.00`  
  `bDeviceClass          239 Miscellaneous Device`  
  `bDeviceSubClass         2`   
  `bDeviceProtocol         1 Interface Association`  
  `bMaxPacketSize0        64`  
  `idVendor           0xcafe`   
  `idProduct          0x4010`   
  `bcdDevice            1.00`  
  `iManufacturer           1 PaniRCorp`  
  `iProduct                2 MicNode_4_Ch`  
  `iSerial                 3 0123456789ABCDEF`  
  `bNumConfigurations      1`  
  `Configuration Descriptor:`  
    `bLength                 9`  
    `bDescriptorType         2`  
    `wTotalLength       0x0099`  
    `bNumInterfaces          2`  
    `bConfigurationValue     1`  
    `iConfiguration          0`   
    `bmAttributes         0x80`  
      `(Bus Powered)`  
    `MaxPower              100mA`  
    `Interface Association:`  
      `bLength                 8`  
      `bDescriptorType        11`  
      `bFirstInterface         0`  
      `bInterfaceCount         2`  
      `bFunctionClass          1 Audio`  
      `bFunctionSubClass       0`   
      `bFunctionProtocol      32`   
      `iFunction               0`   
    `Interface Descriptor:`  
      `bLength                 9`  
      `bDescriptorType         4`  
      `bInterfaceNumber        0`  
      `bAlternateSetting       0`  
      `bNumEndpoints           0`  
      `bInterfaceClass         1 Audio`  
      `bInterfaceSubClass      1 Control Device`  
      `bInterfaceProtocol     32`   
      `iInterface              0`   
      `AudioControl Interface Descriptor:`  
        `bLength                 9`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      1 (HEADER)`  
        `bcdADC               2.00`  
        `bCategory               3`  
        `wTotalLength       0x0048`  
        `bmControls           0x00`  
      `AudioControl Interface Descriptor:`  
        `bLength                 8`  
        `bDescriptorType        36`  
        `bDescriptorSubtype     10 (CLOCK_SOURCE)`  
        `bClockID                4`  
        `bmAttributes            1 Internal fixed clock`   
        `bmControls           0x01`  
          `Clock Frequency Control (read-only)`  
        `bAssocTerminal          1`  
        `iClockSource            0`   
      `AudioControl Interface Descriptor:`  
        `bLength                17`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      2 (INPUT_TERMINAL)`  
        `bTerminalID             1`  
        `wTerminalType      0x0201 Microphone`  
        `bAssocTerminal          3`  
        `bCSourceID              4`  
        `bNrChannels             4`  
        `bmChannelConfig    0x00000000`  
        `iChannelNames           0`   
        `bmControls         0x0004`  
          `Connector Control (read-only)`  
        `iTerminal               0`   
      `AudioControl Interface Descriptor:`  
        `bLength                12`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      3 (OUTPUT_TERMINAL)`  
        `bTerminalID             3`  
        `wTerminalType      0x0101 USB Streaming`  
        `bAssocTerminal          1`  
        `bSourceID               2`  
        `bCSourceID              4`  
        `bmControls         0x0000`  
        `iTerminal               0`   
      `AudioControl Interface Descriptor:`  
        `bLength                26`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      6 (FEATURE_UNIT)`  
        `bUnitID                 2`  
        `bSourceID               1`  
        `bmaControls(0)     0x0000000f`  
          `Mute Control (read/write)`  
          `Volume Control (read/write)`  
        `bmaControls(1)     0x0000000f`  
          `Mute Control (read/write)`  
          `Volume Control (read/write)`  
        `bmaControls(2)     0x0000000f`  
          `Mute Control (read/write)`  
          `Volume Control (read/write)`  
        `bmaControls(3)     0x0000000f`  
          `Mute Control (read/write)`  
          `Volume Control (read/write)`  
        `bmaControls(4)     0x0000000f`  
          `Mute Control (read/write)`  
          `Volume Control (read/write)`  
        `iFeature                0`   
    `Interface Descriptor:`  
      `bLength                 9`  
      `bDescriptorType         4`  
      `bInterfaceNumber        1`  
      `bAlternateSetting       0`  
      `bNumEndpoints           0`  
      `bInterfaceClass         1 Audio`  
      `bInterfaceSubClass      2 Streaming`  
      `bInterfaceProtocol     32`   
      `iInterface              0`   
    `Interface Descriptor:`  
      `bLength                 9`  
      `bDescriptorType         4`  
      `bInterfaceNumber        1`  
      `bAlternateSetting       1`  
      `bNumEndpoints           1`  
      `bInterfaceClass         1 Audio`  
      `bInterfaceSubClass      2 Streaming`  
      `bInterfaceProtocol     32`   
      `iInterface              0`   
      `AudioStreaming Interface Descriptor:`  
        `bLength                16`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      1 (AS_GENERAL)`  
        `bTerminalLink           3`  
        `bmControls           0x00`  
        `bFormatType             1`  
        `bmFormats          0x00000001`  
          `PCM`  
        `bNrChannels             4`  
        `bmChannelConfig    0x00000000`  
        `iChannelNames           0`   
      `AudioStreaming Interface Descriptor:`  
        `bLength                 6`  
        `bDescriptorType        36`  
        `bDescriptorSubtype      2 (FORMAT_TYPE)`  
        `bFormatType             1 (FORMAT_TYPE_I)`  
        `bSubslotSize            2`  
        `bBitResolution         16`  
      `Endpoint Descriptor:`  
        `bLength                 7`  
        `bDescriptorType         5`  
        `bEndpointAddress     0x81  EP 1 IN`  
        `bmAttributes            5`  
          `Transfer Type            Isochronous`  
          `Synch Type               Asynchronous`  
          `Usage Type               Data`  
        `wMaxPacketSize     0x0188  1x 392 bytes`  
        `bInterval               1`  
        `AudioStreaming Endpoint Descriptor:`  
          `bLength                 8`  
          `bDescriptorType        37`  
          `bDescriptorSubtype      1 (EP_GENERAL)`  
          `bmAttributes         0x00`  
          `bmControls           0x00`  
          `bLockDelayUnits         0 Undefined`  
          `wLockDelay         0x0000`  
`Device Status:     0x0000`  
  `(Bus Powered)`

## ALSA enumeration {#alsa-enumeration}

Note that this example comes from a laptop connected to the microphone through a USB dock, and so there are more listed audio devices than would be expected on the Raspberry Pi.

`arecord -l -L`  
`null`  
    `Discard all samples (playback) or generate zero samples (capture)`  
`default`  
    `Playback/recording through the PulseAudio sound server`  
`samplerate`  
    `Rate Converter Plugin Using Samplerate Library`  
`speexrate`  
    `Rate Converter Plugin Using Speex Resampler`  
`jack`  
    `JACK Audio Connection Kit`  
`oss`  
    `Open Sound System`  
`pulse`  
    `PulseAudio Sound Server`  
`upmix`  
    `Plugin for channel upmix (4,6,8)`  
`vdownmix`  
    `Plugin for channel downmix (stereo) with a simple spacialization`  
`hw:CARD=sofhdadsp,DEV=0`  
    `sof-hda-dsp,`   
    `Direct hardware device without any conversions`  
`hw:CARD=sofhdadsp,DEV=1`  
    `sof-hda-dsp,`   
    `Direct hardware device without any conversions`  
`hw:CARD=sofhdadsp,DEV=6`  
    `sof-hda-dsp,`   
    `Direct hardware device without any conversions`  
`hw:CARD=sofhdadsp,DEV=7`  
    `sof-hda-dsp,`   
    `Direct hardware device without any conversions`  
`plughw:CARD=sofhdadsp,DEV=0`  
    `sof-hda-dsp,`   
    `Hardware device with all software conversions`  
`plughw:CARD=sofhdadsp,DEV=1`  
    `sof-hda-dsp,`   
    `Hardware device with all software conversions`  
`plughw:CARD=sofhdadsp,DEV=6`  
    `sof-hda-dsp,`   
    `Hardware device with all software conversions`  
`plughw:CARD=sofhdadsp,DEV=7`  
    `sof-hda-dsp,`   
    `Hardware device with all software conversions`  
`sysdefault:CARD=sofhdadsp`  
    `sof-hda-dsp,`   
    `Default Audio Device`  
`dsnoop:CARD=sofhdadsp,DEV=0`  
    `sof-hda-dsp,`   
    `Direct sample snooping device`  
`dsnoop:CARD=sofhdadsp,DEV=1`  
    `sof-hda-dsp,`   
    `Direct sample snooping device`  
`dsnoop:CARD=sofhdadsp,DEV=6`  
    `sof-hda-dsp,`   
    `Direct sample snooping device`  
`dsnoop:CARD=sofhdadsp,DEV=7`  
    `sof-hda-dsp,`   
    `Direct sample snooping device`  
`usbstream:CARD=sofhdadsp`  
    `sof-hda-dsp`  
    `USB Stream Output`  
`hw:CARD=Dock,DEV=0`  
    `WD19 Dock, USB Audio`  
    `Direct hardware device without any conversions`  
`plughw:CARD=Dock,DEV=0`  
    `WD19 Dock, USB Audio`  
    `Hardware device with all software conversions`  
`sysdefault:CARD=Dock`  
    `WD19 Dock, USB Audio`  
    `Default Audio Device`  
`front:CARD=Dock,DEV=0`  
    `WD19 Dock, USB Audio`  
    `Front output / input`  
`dsnoop:CARD=Dock,DEV=0`  
    `WD19 Dock, USB Audio`  
    `Direct sample snooping device`  
`usbstream:CARD=Dock`  
    `WD19 Dock`  
    `USB Stream Output`  
`hw:CARD=MicNode4Ch,DEV=0`  
    `MicNode_4_Ch, USB Audio`  
    `Direct hardware device without any conversions`  
`plughw:CARD=MicNode4Ch,DEV=0`  
    `MicNode_4_Ch, USB Audio`  
    `Hardware device with all software conversions`  
`sysdefault:CARD=MicNode4Ch`  
    `MicNode_4_Ch, USB Audio`  
    `Default Audio Device`  
`front:CARD=MicNode4Ch,DEV=0`  
    `MicNode_4_Ch, USB Audio`  
    `Front output / input`  
`dsnoop:CARD=MicNode4Ch,DEV=0`  
    `MicNode_4_Ch, USB Audio`  
    `Direct sample snooping device`  
`usbstream:CARD=MicNode4Ch`  
    `MicNode_4_Ch`  
    `USB Stream Output`  
`**** List of CAPTURE Hardware Devices ****`  
`card 0: sofhdadsp [sof-hda-dsp], device 0: HDA Analog (*) []`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`  
`card 0: sofhdadsp [sof-hda-dsp], device 1: HDA Digital (*) []`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`  
`card 0: sofhdadsp [sof-hda-dsp], device 6: DMIC (*) []`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`  
`card 0: sofhdadsp [sof-hda-dsp], device 7: DMIC16kHz (*) []`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`  
`card 1: Dock [WD19 Dock], device 0: USB Audio [USB Audio]`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`  
`card 2: MicNode4Ch [MicNode_4_Ch], device 0: USB Audio [USB Audio]`  
  `Subdevices: 1/1`  
  `Subdevice #0: subdevice #0`