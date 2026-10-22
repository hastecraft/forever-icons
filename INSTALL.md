# forever-icons

Every icon in WoW Forever, upscaled 4× (64×64 → 256×256) with sharp mipmaps.

There are two packs. Install one of them:

- **forever-icons**: the icons as Blizzard drew them, with the game's grey bevel.
- **forever-icons-black-frame**: the grey bevel is cropped off and replaced with a thin black frame. Round and
  shaped icons, like tracking icons and faction crests, are the same as in the main pack.

All icons are the work of Blizzard Entertainment and all credit for them belongs to Blizzard's artists. This is an
unofficial, non-commercial fan project, not affiliated with or endorsed by Blizzard. I claim no rights to the icons.
World of Warcraft and Blizzard Entertainment are trademarks or registered trademarks of Blizzard Entertainment, Inc.

## Install

1. Close the game.
2. Find your game folder: the one holding `Interface` and the game's `.exe`, for example
   `C:\Program Files (x86)\World of Warcraft\_forever_`.
3. Copy the `Interface` folder from this zip into it, merging with the folder that's already there.
   You should end up with `...\_forever_\Interface\Icons\` full of `.blp` files.
4. Start the game.

To switch to the other pack, do the same with its zip and let it replace the files.

## Uninstall

Close the game and delete the `Interface\Icons` folder from your game folder. The game falls back to its own icons.

## Notes

- The icons only replace the game's art on your own screen. Nothing is sent to the server.
- A patch that adds or changes icons won't update these files. Changed icons will show the old picture until the
  pack is rebuilt for the new build.
- UI addons that skin action buttons (ElvUI, for example) already trim the icon edges and draw their own border.
  With those the black frame gets trimmed away, so use the main pack.
- Each icon uses more video memory than the original's 4 KB: about 69 KB in the main pack and 44 KB in the
  black-frame pack, which needs no transparency. Only icons the game has loaded count, so a few hundred icons come
  to about 5 to 20 MB of video memory. On disk the main pack takes 2 GB and the black-frame pack 1.3 GB.
