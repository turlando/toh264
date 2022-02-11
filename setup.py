from setuptools import setup

setup(
    name='toh264',
    version='0.0.2',
    url='http://github.com/turlando/toh264',

    author='Tancredi Orlando',
    author_email='tancredi.orlando@gmail.com',

    description='Quick and dirty transcoding',
    long_description=open('README.rst').read(),

    license='AGPLv3',

    classifiers=[
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Programming Language :: Python :: 3',
    ],

    python_requires='>=3.6, <4',

    py_modules=['toh264'],
    entry_points={'console_scripts': ['toh264=toh264:main']}
)
