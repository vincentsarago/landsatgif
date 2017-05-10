
import os

from setuptools import setup, find_packages

with open('landsatgif/__init__.py') as f:
    for line in f:
        if line.find("__version__") >= 0:
            version = line.split("=")[1].strip()
            version = version.strip('"')
            version = version.strip("'")
            continue


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(name='landsatgif',
    version=version,
    description=u"",
    long_description=u"",
    classifiers=[
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.6'
    ],
    keywords='landsat to gif',
    author=u"Vincent Sarago",
    author_email='contact@remotepixel.ca',
    url='https://github.com/remotepixel/landsatgif',
    license='MIT',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=read('requirements.txt').splitlines(),
    extras_require={
        'test': ['pytest', 'pytest-cov', 'codecov'],
    },
    entry_points="""
    [console_scripts]
    landsatgif=landsatgif.cli:main
    """
    )
