ReportBro Server (Tornado)
==========================

This is a simple Python webserver using Tornado to generate reports with ReportBro.

You can use this webserver as a starting point if you have no existing Python application
and only need a report server. You can add your own methods to this script
where you query application data for a specific report and directly return
the generated report. Instead of the in-memory sqlite db you need to connect to your
application database.

In case you already have a Python web application it is recommended to directly
integrate ReportBro into your existing app. Have look at the demo apps available for
`Django <https://github.com/jobsta/albumapp-django.git>`_, 
`Flask <https://github.com/jobsta/albumapp-flask.git>`_ and
`web2py <https://github.com/jobsta/albumapp-web2py.git>`_.

All Instructions in this file are for a Linux/Mac shell but the commands should
be easy to adapt for Windows.

Installation
------------

Clone the git repository and change into the created directory:

.. code:: shell

    $ git clone https://github.com/jobsta/reportbro-server-tornado.git
    $ cd reportbro-server-tornado

Create a virtual environment called env:

.. code:: shell

    $ python3 -m venv env

Activate the virtual environment:

.. code:: shell

    $ . env/bin/activate

Install all required dependencies:

.. code:: shell

    $ pip install reportbro-lib SQLAlchemy tornado

Configuration
-------------

You can change the constants SERVER_PORT, SERVER_PATH, MAX_CACHE_SIZE at the beginning of the script.

Run Server
----------

Activate the virtual environment (if not already active):

.. code:: shell

    $ . env/bin/activate

Start the ReportBro server:

.. code:: shell

    $ python reportbro_server.py

Now your server is running and report requests can be sent to:
http://127.0.0.1:8000/reportbro/report/run

Python Coding Style
-------------------

The `PEP 8 (Python Enhancement Proposal) <https://www.python.org/dev/peps/pep-0008/>`_
standard is used which is the de-facto code style guide for Python. An easy-to-read version
of PEP 8 can be found at https://pep8.org/
