﻿# Editor_indice_Py

[![Python](https://img.shields.io/badge/Python-3.11.9-blue)](https://www.python.org/downloads/release/python-3119/)
[![GitHub Release](https://img.shields.io/github/v/release/kastomd/Editor_indice_Py)](https://github.com/kastomd/Editor_indice_Py/releases/latest)

## Features
The program is a tool developed in Python designed to manipulate the general indices of a binary container file called packfile.bin. This file serves as a package that stores multiple resources, such as data, images, sounds, or configurations, organized in a specific format.

The main goal of the program is to allow users to edit, add, or delete entries in the file's indices

You can also try the **Extract Tool** section, which allows you to extract and compress PCK files, PPHD files, character patches, and other game files.

## Download
To get started, you can download the latest version of the app from the following link:

[![GitHub All Releases](https://img.shields.io/github/v/release/kastomd/Editor_indice_Py?style=for-the-badge)](https://github.com/kastomd/Editor_indice_Py/releases/latest)

If you encounter any errors, please install the following redistributable packages.

[Microsoft Visual C++ 2005 SP1 Redistributable Package (x86)](https://www.microsoft.com/en-us/download/details.aspx?id=26347)

[Microsoft Visual C++ 2005 SP1 Redistributable Package (x64)](https://www.microsoft.com/en-us/download/details.aspx?id=26347)

## How to convert WAV audio files to AT3

You can drag and drop the audio files onto the index editor window, and the conversion will automatically start—whether it's from WAV to AT3 or AT3 to WAV.

Or use the option **Tool > Convert audio WAV or AT3**

**Important**

The conversion from **WAV to AT3** must follow this format exactly. Do not attempt to change any parameters, otherwise the tool will throw an error.

WAV format:

> Codec: 16-bit PCM

> Sample rate: 44100 Hz

> Channels: 2 (stereo)

### Compress the ISO including the WAV audio files

You can also place the WAV file inside the **ext_PACKFILE_BIN_yourisoname** folder and check this box so the tool converts the WAV to AT3 and creates the ISO.
Obviously, the WAV file must have the same name as the file it is going to replace.

![image](https://github.com/user-attachments/assets/975d571c-347c-49b0-ad80-fb90f3c39524)
![image](https://github.com/user-attachments/assets/7629b050-cea0-4f3d-8152-43a0d22ff208)

In Tenkaichi Tag Team, the game loops the music automatically. Even if your WAV audio contains the SMPL chunk, it won’t be used because the game only reads the audio data in AT3 format—the header is not used in this game.


### How to convert WAV audio to AT3 for story mode or characters
 In your .wav file, add ```_m_``` at the end of the name, then continue compressing the ISO. The audio will automatically adapt for story mode or character mode
 
 Make sure your audio is sped up to x2.

 Example:
 ```
// If it's for converting WAV  to AT3 story mode files or characters
 1778_6F2_m_.wav

 //  If it's for converting AT3 story mode files to WAV
 1827_723_m_.unk
 ```

 Do not apply this to music, as it will remove the stereo from the audio and make it sound a bit strange.

 In Tool > **Add/Remove ```_m_``` to files**, you can add or remove the ```_m_``` from the files you want.


## How to convert VAG to WAV with the extract tool

For this case, you need to obtain the full PPHD file. It is also compatible with Naruto Shippuden: Ultimate Ninja Impact by checking the "PPHD narut" box for that case. If the file is from Tenkaichi Tag Team, make sure that option is unchecked.

To export audio as WAV, the Process WAV box must be checked—whether you're exporting the file or rebuilding it.

![image](https://github.com/user-attachments/assets/7b757ad8-071a-4de5-886d-51402769d847)

The WAV format must be as follows.
If your file does not follow this format, the tool will automatically convert it:

> Codec: 16-bit PCM

> Sample rate: Any value you prefer

> Channels: 1 (mono)

### How can I loop the Vag audio?

First, locate the ***metadato_for_wav.json*** file. Inside, you'll find the audios that include loop information.
If your WAV does not have a loop, you can add it using this file—do not use another program.

You only need to modify **loop_start** and **loop_end**.

If you want the entire audio to loop, use **"force_loop": "-L"**.

To remove the loop (if it exists), use **"force_loop": "-1"**.

When **force_loop** is empty, the tool will use the assigned **loop_start** and **loop_end**.

Example:

```
"23-17.vag": {
        "loop_start": "0:00.003", // m:s.ms
        "loop_end": "0:01.239",
        "duration": "0:01.239", // It's just visual, it doesn't affect anything
        "force_loop": ""
    }
```
**Reminder:** this file only affects WAV audio files, resulting in a VAG file with a loop. You cannot assign a loop directly to a VAG file.

### How to edit the .txt files of Tenkaichi Tag Team

Just drag and extract the file.

Make sure to save the .txt files using one of the formats listed here. Do not use any other encoding:

Accepted encodings:

- UTF-8

- UTF-8 with BOM

- UTF-16 Big Endian with BOM

- UTF-16 Little Endian with BOM

## Clone Project

Create a new fork of this repository.
Or simply clone the project (not recommended if you plan to add features).

Make sure you are using Python 3.11.9.

You will need to install the requirements:

```
pip install -r requirements.txt
```

Then you'll need the CLI tools.
These are required if you plan to work with audio files; otherwise, you can skip them.

P.S.: Don’t expect to see pro-level code.
