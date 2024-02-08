from setuptools import setup, find_packages
setup(
    name='pyvaheat',
    version='0.1.0',
    description='Wapper class for VAHEAT serial controller API',
    author='Ikuo Obataya',
    author_email='obataya@qd-japan.com',
    url='https://github.com/iobataya/pyvaheat.git',
    packages=find_packages(),
    long_description='This class and CLI can controll VAHEAT controller on python.',
    install_requires=[
        'pyserial',
    ]
)