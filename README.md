# Mt Hood night screen

An overnight display for a jailbroken Kindle that shows the Timberline Lodge
Palmer/Silcox webcam by day. After dark it shows the dark-sky window (astronomical
night with the moon down), cloud cover, moon phase, the next meteor shower peak,
Kp index, overnight low, sunrise and freezing level, plus new snow and summit wind
in winter.

A scheduled workflow runs `render.py` every 30 minutes and publishes to GitHub Pages:

- `night.png`: 800x600, for viewing
- `night-kindle.png`: rotated for the Kindle's portrait panel

Data comes from keyless public APIs: [Open-Meteo](https://open-meteo.com),
[USNO](https://aa.usno.navy.mil/data/api), [sunrise-sunset.org](https://sunrise-sunset.org/api)
and [NOAA SWPC](https://services.swpc.noaa.gov). Meteor shower peaks are from the IMO
2026 calendar and need refreshing each year.

Barlow font by The Barlow Project Authors, SIL Open Font License 1.1 (`fonts/OFL.txt`).
