/* The 5 players, confirmed by Natalie Nov 8, 2026. All NA, Mayhem only.
   riot_id is the canonical ID from players.yaml (used to match the
   export to the repo). url is the EXACT profile URL Natalie sent —
   PlayARAM lowercases the name in the URL (PikabUwU -> pikabuwu,
   "Vincent Chan" -> vincent%20chan, # -> %23). Do not "fix" the case:
   these URLs were verified against the ones she pasted. */
const MAYHEM_PLAYERS = [
  {
    display_name: "I3i3oy",
    riot_id: "i3i3oy#NA1",
    url: "https://playaram.gg/en/profile/na/i3i3oy%23NA1",
  },
  {
    display_name: "Vincent Chan",
    riot_id: "Vincent Chan#NA1",
    url: "https://playaram.gg/en/profile/na/vincent%20chan%23NA1",
  },
  {
    display_name: "CreamiNataella",
    riot_id: "CreamiNataella#NA1",
    url: "https://playaram.gg/en/profile/na/creaminataella%23NA1",
  },
  {
    display_name: "Ohwutahel",
    riot_id: "Ohwutahel#NA1",
    url: "https://playaram.gg/en/profile/na/ohwutahel%23NA1",
  },
  {
    display_name: "PikabUwU",
    riot_id: "PikabUwU#NA1",
    url: "https://playaram.gg/en/profile/na/pikabuwu%23NA1",
  },
];
