"""Test setup. Maths Fundamentals is off by default on the real site; its own tests switch it on."""
import os

os.environ.setdefault('FUNDAMENTALS_ENABLED', '1')
