#!/usr/bin/env python3
import os
import re
import sys
import wave
import shutil
import subprocess
import argparse
import stat
from pathlib import Path
from sys import platform


def apply_offset(input_wav: Path, output_wav: Path, delay_ms: int):
    """Apply a positive or negative millisecond delay to a WAV file."""
    import wave
    with wave.open(str(input_wav), 'rb') as infile:
        channels = infile.getnchannels()
        sampwidth = infile.getsampwidth()
        framerate = infile.getframerate()
        total_frames = infile.getnframes()
        comptype = infile.getcomptype()
        compname = infile.getcompname()

        offset_frames = int(framerate * abs(delay_ms) / 1000.0)

        if delay_ms < 0:
            # Negative => trim the start
            if offset_frames >= total_frames:
                raise ValueError(
                    f"Cannot trim {delay_ms} ms; file is too short."
                )
            infile.setpos(offset_frames)
            audio_data = infile.readframes(total_frames - offset_frames)
        elif delay_ms > 0:
            # Positive => prepend silence
            silence = b"\x00" * offset_frames * channels * sampwidth
            audio_data = infile.readframes(total_frames)
            audio_data = silence + audio_data
        else:
            # Zero => just read as-is
            audio_data = infile.readframes(total_frames)

    with wave.open(str(output_wav), 'wb') as outfile:
        outfile.setnchannels(channels)
        outfile.setsampwidth(sampwidth)
        outfile.setframerate(framerate)
        outfile.setcomptype(comptype, compname)
        outfile.writeframes(audio_data)


def gather_vgs_files(root_dir: Path):
    """
    Find .vgs files in a 'songs' subfolder; ignore:
      - 'tutorial' or 'sfx' subpaths,
      - practice variants ending with _p*.vgs (e.g. _p50, _p85, etc.)
    """
    all_vgs = list(root_dir.rglob("*.vgs"))
    filtered = []
    for vgs_path in all_vgs:
        parts_lower = [p.lower() for p in vgs_path.parts]
        stem_lower = vgs_path.stem.lower()

        # Ignore tutorial/sfx
        if "tutorial" in parts_lower or "sfx" in parts_lower:
            continue

        # Only want files within 'songs' subfolder
        if "songs" not in parts_lower:
            continue

        # Ignore any that end with "_p" + optional digits (e.g. _p50, _p85, etc.)
        if re.search(r'_p\d{2}$', stem_lower):
            continue

        filtered.append(vgs_path)
    return filtered


def process_vgs_files(root_dir: Path, delay_ms: int, rockaudio: Path):
    """Convert .vgs to WAV, apply delay, then convert back to .vgs."""
    vgs_files = gather_vgs_files(root_dir)
    if not vgs_files:
        print(f"No eligible .vgs files found in {root_dir}.")
        return

    for vgs_path in vgs_files:
        print(f"\nProcessing {vgs_path}")
        print("\n--- THIS WILL TAKE SOME TIME ---")
        print("\n--- DO NOT CLOSE THIS WINDOW ---\n")

        temp_wav = vgs_path.with_name(f"{vgs_path.stem}_temp.wav")
        processed_wav = vgs_path.with_name(f"{vgs_path.stem}_temp_processed.wav")
        temp_vgs = vgs_path.with_name(f"{vgs_path.stem}_temp.vgs")

        try:
            print("  Converting to WAV...")
            subprocess.run(
                [str(rockaudio), "convert", str(vgs_path), str(temp_wav)],
                check=True
            )

            print(f"  Applying delay: {delay_ms} ms")
            apply_offset(temp_wav, processed_wav, delay_ms)

            print("  Converting back to VGS...")
            subprocess.run(
                [str(rockaudio), "convert", str(processed_wav), str(temp_vgs)],
                check=True
            )

            print("  Replacing original VGS...")
            os.replace(temp_vgs, vgs_path)
        except Exception as e:
            print(f"  Error: {e}")
        finally:
            if temp_wav.exists():
                temp_wav.unlink()
            if processed_wav.exists():
                processed_wav.unlink()


def extract_ark(hdr_path: Path, arkhelper: Path, temp_dir: Path):
    """Extract .ark/.hdr to a temporary directory using arkhelper, and place a marker file."""
    print(f"Extracting from {hdr_path} to {temp_dir}")
    temp_dir.mkdir(exist_ok=True, parents=True)
    subprocess.run(
        [str(arkhelper), "ark2dir", str(hdr_path), str(temp_dir), "-a"],
        check=True
    )

    # Create a blank marker file to show we actually unpacked
    marker_file = temp_dir / "ark.txt"
    if not marker_file.exists():
        marker_file.touch()


def repack_ark(temp_dir: Path, hdr_folder: Path, arkhelper: Path):
    """
    Repack files using arkhelper, creating MAIN.HDR/MAIN.ARK in hdr_folder
    but only if our marker file (ark.txt) exists, which indicates we unpacked.
    """
    marker_file = temp_dir / "ark.txt"
    if not marker_file.exists():
        print(f"Skipping repack in {temp_dir}; marker file 'ark.txt' not found.")
        return

    print(f"Repacking from {temp_dir} into {hdr_folder}")
    subprocess.run(
        [
            str(arkhelper), "dir2ark", str(temp_dir), str(hdr_folder),
            "-n", "MAIN", "-s", "4073741823"
        ],
        check=True
    )


def parse_system_cnf_for_label(system_cnf: Path) -> str:
    r"""
    Parse the SYSTEM.CNF to find the volume label from the BOOT2 line.
    Example line: BOOT2 = cdrom0:\SLUS_215.86;1
    We want the 'SLUS_215.86' part (before ';').
    """
    if not system_cnf.exists():
        return ""

    with system_cnf.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.upper().startswith("BOOT2"):
                parts = line.split("\\")
                if len(parts) > 1:
                    remainder = parts[-1].split(";")[0]
                    return remainder.strip()
    return ""


def cleanup_build_iso(main_folder: Path):
    """
    Clean up temporary files created during the ISO build:
    - imgburn.exe, imgburn.ini, DELETEME log from main_folder
    - DVD_Sectors.Bin from the top-level folder.
    """
    imgburn_exe_dest = main_folder / "imgburn.exe"
    imgburn_ini_dest = main_folder / "imgburn.ini"
    if imgburn_exe_dest.exists():
        imgburn_exe_dest.unlink()
    if imgburn_ini_dest.exists():
        imgburn_ini_dest.unlink()

    delete_me_path = main_folder / "DELETEME"
    if delete_me_path.exists():
        delete_me_path.unlink()

    dvd_sectors = main_folder.parent / "DVD_Sectors.Bin"
    if dvd_sectors.exists():
        dvd_sectors.unlink()


def build_iso(main_folder: Path, dep_dir: Path):
    """
    Ask user if they want to create an ISO now. If yes:
      - Parse SYSTEM.CNF for volume label
      - Copy imgburn.exe/imgburn.ini into main folder
      - Dynamically build /SRC list from everything in main folder
      - Run ImgBurn
      - Move the ISO up one directory after completion
      - Always run ps2master.exe on the ISO if it exists
      - Finally, clean up imgburn.exe, imgburn.ini, the DELETEME log, and DVD_Sectors.Bin
    """
    choice = input("\nWould you like to create an ISO now? (y/n): ").strip().lower()
    if not choice.startswith("y"):
        print("Skipping ISO creation.")
        cleanup_build_iso(main_folder)
        return

    system_cnf = main_folder / "SYSTEM.CNF"
    if not system_cnf.exists():
        print("[ERROR] SYSTEM.CNF not found. Cannot build ISO.")
        cleanup_build_iso(main_folder)
        return

    volume_label = parse_system_cnf_for_label(system_cnf)
    if not volume_label:
        print("[ERROR] Could not parse BOOT2 line from SYSTEM.CNF. Cannot build ISO.")
        cleanup_build_iso(main_folder)
        return

    # Copy imgburn.exe / imgburn.ini
    imgburn_exe_source = dep_dir / "imgburn.exe"
    imgburn_ini_source = dep_dir / "imgburn.ini"
    if not imgburn_exe_source.exists():
        print(f"[ERROR] Missing {imgburn_exe_source}")
        cleanup_build_iso(main_folder)
        return
    if not imgburn_ini_source.exists():
        print(f"[ERROR] Missing {imgburn_ini_source}")
        cleanup_build_iso(main_folder)
        return

    imgburn_exe_dest = main_folder / "imgburn.exe"
    imgburn_ini_dest = main_folder / "imgburn.ini"

    shutil.copyfile(imgburn_exe_source, imgburn_exe_dest)
    shutil.copyfile(imgburn_ini_source, imgburn_ini_dest)

    src_items = []
    for item in main_folder.iterdir():
        if item.name in [".gitkeep", "imgburn.exe", "imgburn.ini"]:
            continue
        if item.is_dir() and (item.name.startswith("temp_") or item.name == "_processed_original_isos"):
            continue
        src_items.append(item.name)

    src_flag = "|".join(src_items)
    iso_name = f"{volume_label}.iso"
    iso_out_path = main_folder / iso_name

    if platform == "windows":
        dest_arg = str(iso_out_path) # This might be redundant, not sure.
    else:
        dest_arg = iso_name
        os.chmod(imgburn_exe_dest, os.stat(imgburn_exe_dest).st_mode | stat.S_IXUSR) # Add the executable permission to the imgburn exe

    

    cmd = [
        str(imgburn_exe_dest),
        "/SETTINGS", "./imgburn.ini",
        "/PORTABLE",
        "/MODE", "BUILD",
        "/BUILDMODE", "IMAGEFILE",
        "/FILESYSTEM", "ISO9660 + UDF",
        "/UDFREV", "1.02",
        "/VOLUMELABEL", volume_label,
        "/OVERWRITE", "YES",
        "/ROOTFOLDER", "TRUE",
        "/NOIMAGEDETAILS",
        "/SRC", src_flag,
        "/DEST", dest_arg,
        "/START",
        "/CLOSE",
        "/LOG", "DELETEME"
    ]

    print("\nRunning ImgBurn to create ISO... (this may take a while)")
    try:
        subprocess.run(cmd, cwd=str(main_folder), check=True)
        print("ISO creation completed.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ImgBurn failed with return code {e.returncode}")
    except Exception as ex:
        print(f"[ERROR] Unexpected error while creating ISO: {ex}")
    finally:
        if iso_out_path.exists():
            parent_dir = main_folder.parent
            final_iso = parent_dir / iso_name
            shutil.move(str(iso_out_path), str(final_iso))
            print(f"Output ISO: {final_iso}\n")
            cleanup_build_iso(main_folder)
            ps2master_exe = dep_dir / "ps2master.exe"
            if not ps2master_exe.exists():
                print(f"[ERROR] ps2master.exe not found at {ps2master_exe}")
            else:
                try:
                    subprocess.run(
                        [str(ps2master_exe), final_iso.name],
                        cwd=str(final_iso.parent),
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] ps2master.exe failed with return code {e.returncode}")
                except Exception as ex:
                    print(f"[ERROR] Unexpected error running ps2master.exe: {ex}")


def extract_any_isos(main_folder: Path, seven_z: Path):
    """
    Look for .iso files in 'main_folder' (excluding the _processed_original_isos folder),
    extract them directly into 'main_folder', then move the ISO to _processed_original_isos.
    """
    if not seven_z.exists():
        print(f"[WARN] 7z.exe not found at {seven_z}; cannot extract ISO files.")
        return

    processed_folder = main_folder / "_processed_original_isos"
    processed_folder.mkdir(exist_ok=True)

    for iso_file in main_folder.glob("*.iso"):
        if iso_file.parent == processed_folder:
            continue

        print(f"\nDetected ISO: {iso_file.name}")
        print("Extracting contents directly into the main folder (no subfolder)...")
        try:
            subprocess.run(
                [
                    str(seven_z), "x",
                    str(iso_file),
                    f"-o{str(main_folder)}",
                    "-y"
                ],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Extraction of {iso_file} failed with return code {e.returncode}")
            continue
        except Exception as ex:
            print(f"[ERROR] Unexpected error extracting {iso_file}: {ex}")
            continue

        target = processed_folder / iso_file.name
        iso_file.rename(target)
        print(f"Moved original ISO to: {target}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Extract, offset, and repack .vgs files within a main HDR/ARK set (or extracted ISO). Optionally build an ISO."
    )
    parser.add_argument(
        "-d", "--delay",
        type=int,
        default=None,
        help="Delay in ms (negative = trim, positive = add silence). Default prompt is -60 if not provided."
    )
    parser.add_argument(
        "--skip", "-s",
        action="store_true",
        help="Skip VGS extraction/offset processing and jump straight to optional ISO creation."
    )

    args = parser.parse_args()

    script_dir = Path(__file__).parent.resolve()
    dep_dir = script_dir / "z_dependencies"
    rockaudio = dep_dir / "RockAudio.exe"
    arkhelper = dep_dir / "arkhelper.exe"
    seven_z = dep_dir / "7z.exe"  # for ISO extraction

    root_path = script_dir / "main"
    if not root_path.exists():
        print(f"[ERROR] The 'main' folder does not exist at: {root_path}")
        sys.exit(1)

    if args.delay is None:
        print("\nPS2 Guitar Hero Sync Utility (resyncinator) by jnack")
        print("Use negative values to trim the start (counter PS2/PCSX2 delay).")
        print("Use positive values to add silence at the start.")
        raw_input_val = input("Enter delay (ms) [default: -60]: ").strip()
        if not raw_input_val:
            delay_ms = -60
        else:
            try:
                delay_ms = int(raw_input_val)
            except ValueError:
                print("Invalid numeric value for delay.")
                sys.exit(1)
    else:
        delay_ms = args.delay

    extract_any_isos(root_path, seven_z)

    if args.skip:
        print("Skipping all VGS extraction/offset processing.")
        build_iso(root_path, dep_dir)
        sys.exit()

    main_hdrs = list(root_path.rglob("MAIN.HDR"))
    for hdr_path in main_hdrs:
        hdr_folder = hdr_path.parent
        ark_candidates = list(hdr_folder.glob("MAIN*.ARK"))
        if not ark_candidates:
            continue

        temp_out = hdr_folder / "temp_out"
        print(f"\nExtracting ARK from {hdr_path} to apply VGS processing in {hdr_folder} ...")
        extract_ark(hdr_path, arkhelper, temp_out)

        print("\n--- Processing VGS files in extracted ARK ---")
        process_vgs_files(temp_out, delay_ms, rockaudio)

        print("\n--- Repacking ARK with updated VGS ---")
        repack_ark(temp_out, hdr_folder, arkhelper)
        shutil.rmtree(temp_out, ignore_errors=True)

    print("\n----- Processing VGS files in main folder (non-ARK) -----")
    process_vgs_files(root_path, delay_ms, rockaudio)

    build_iso(root_path, dep_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
