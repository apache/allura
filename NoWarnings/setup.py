try:
    import ez_setup
    ez_setup.use_setuptools()
except ImportError:
    pass

from setuptools import setup

setup(
    name='NoWarnings plugin',
    version='1.0',
    author='Wolf',
    author_email='wolf@geek.net',
    description='A nose plugin to squelch warnings',
    license='GPL',
    py_modules=['nowarnings'],
    entry_points={
        'nose.plugins.0.10': [
            'nowarnings = nowarnings:NoWarnings'
        ]
    }
)
