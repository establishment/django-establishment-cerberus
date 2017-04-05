# Establishment Django Cerberus Daemon
Cerberus is a daemon for Establishment's django app which answers permission queries over Redis.
This module is absolutely mandatory for 'establishment-nodews' websocket server.

## Installation
Just download the source from git/add this repository as a submodule to any project that also uses or is compatible with `django-establishment`.

## How to run
In order to "link" Cerberus with your own app you have to specify the name of your module in the environment variable ESTABLISHMENT_DJANGO_MODULE before you run the daemon:
```
ESTABLISHMENT_DJANGO_MODULE=csacademy python3 cerberus start
```

## License
The Establishment Framework code (including `django-establishment-cerberus`) is released explicitly under public domain (AKA The Unlicence, I just like public domain more than the term "Unlicence").
There are no ugly copyright headers you need to keep, and you can copy/paste the code without any attribution.
It make it easier to bundle your code, so you know a minimized production js can strip all comments away.
In case you need extra assurance, this software is also licenced under [Creative Commons 0][license-cc0], you can pick your preferred licence.

[license-cc0]: https://creativecommons.org/publicdomain/zero/1.0/
