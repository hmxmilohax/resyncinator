# Repackinator

## Simple tool to add or subtract audio delay in gh1/gh2/gh80s isos

# Requirements
## Windows
* Python
## Linux
* Python
* Wine
* 7-Zip installed in default wineprefix

# Usage
* Drag in a gh1/gh2/gh80s/custom iso into the "main" folder
* Only do one iso at a time
### OR
* Extract **ALL FILES** from your gh1/gh2/gh80s/custom iso to the "main" folder
* Only do one disc at a time
### OR
* add any arbitrary .vgs files to the "main" folder (will skip iso generation)
* open a command prompt to the resyncinator directory `cd C:/path/to/repackinator`
* Run `python repackinator.py`
* Optionally, you can include the desired ms value as an argument (default -60) `python repackinator.py 100`
* Sit back and let the program run to completion
* If your input file is an ISO, you can find your original iso untouched in `/main/_processed_original_isos/`
* When done, you will be asked whether or not to also generate a new ISO
* This ISO will be a PS2 Master Disc ISO, it will work via MechaPWN with no additional patches thanks to included [PS2 Master Disc Patcher](https://www.psx-place.com/threads/playstation-2-master-disc-patcher-for-mechapwn.36547/page-3#post-393254)

# Dependencies
* [arkhelper](https://github.com/PikminGuts92/Mackiloha)
* RockAudio from RockLib (Original Source Unknown)
* Bass (Included with RockLib)
* [imgburn](https://www.imgburn.com/index.php) [v2.5.0](http://www.oldversion.com/windows/imgburn-2-5-0-0)
* [PlayStation 2 Master Disc Patcher](https://www.psx-place.com/threads/playstation-2-master-disc-patcher-for-mechapwn.36547/page-3#post-393254)

# Arguments
* `-d` `--delay` (default -60) ms value for defaulting a ms value without prompting 
* `-s` `--skip` - skips all audio processing steps and jumps straight to iso generation

# Disclaimer
* This script was written with AI assistance. This Readme is not.