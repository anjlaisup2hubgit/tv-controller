## Download

Run `git clone https://github.com/anjlaisup2hubgit/tv-controller.git` to get the app.

## Features

This app turns your phone into a TV remote. You open it in a web browser, and it shows buttons like the ones on a real remote. When you tap a button, the TV does what you asked. It can find your TV by itself, so you do not need to type anything hard. The first time, your TV may ask you to type a short code to say "yes, this phone is allowed". It works with Android TV, Roku, Samsung and LG TVs. Your phone and TV must be on the same Wi-Fi. Some buttons do nothing, and that is normal.

## File tree

```
tv-controller/
├── README.md          This page.
├── CLAUDE.md          Rules for the helper that writes the code.
├── requirements.txt   A shopping list of tools the app needs.
├── vercel.json        Settings for putting the web page online.
├── src/               The brain of the app.
│   ├── server.py      Starts the app and listens for button taps.
│   ├── discover.py    Looks around the Wi-Fi to find TVs.
│   ├── drivers.py     Knows how to talk to each kind of TV.
│   ├── remote.py      Sends the button taps to the TV.
│   ├── store.py       Remembers your TV so it is easy next time.
│   └── components/    Notes about each part of the remote screen.
├── public/            What you see on your phone.
│   ├── index.html     The remote with all its buttons.
│   └── favicon.svg    The tiny picture on the browser tab.
├── certs/             A safe spot for security files.
├── data/              A safe spot for saved settings.
└── docs/
    └── changelog.md   A diary of what was added or changed.
```
