// Modal stacking order. Higher numbers render above lower ones.
// Adjust here only — every Backdrop in the app reads from these.
export const Z_BACKDROP_DEFAULT = 200;  // base modal layer (NoteModal, EditModal)
export const Z_BACKDROP_PANEL   = 210;  // primary panels (Accounts, Sync)
export const Z_BACKDROP_DIALOG  = 215;  // dialogs that may open above a panel (Upload)
export const Z_BACKDROP_TOP     = 220;  // top-most edits launched from a panel (Edit Balance)
