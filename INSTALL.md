# HD icons for WoW Forever

Every icon in the game, redrawn at 4× (64×64 → 256×256) with sharp mipmaps.

## Install

1. Close the game.
2. Find your game folder: the one holding `Interface` and the game's `.exe`, for example
   `C:\Program Files (x86)\World of Warcraft\_classic_beta_`.
3. Copy the `Interface` folder from this zip into it, merging with the folder that's already there.
   You should end up with `...\_classic_beta_\Interface\Icons\` full of `.blp` files.
4. Start the game.

## Uninstall

Close the game and delete the `Interface\Icons` folder from your game folder. The game falls back to its own icons.

## Notes

- The icons only replace the game's art on your own screen. Nothing is sent to the server.
- A patch that adds or changes icons won't update these files. Changed icons will show the old picture until the
  pack is rebuilt for the new build.
- Each icon uses up to 16 times the video memory of the original (about 85 KB instead of 5 KB). Only icons on
  screen are loaded, so this is a few MB in practice.
