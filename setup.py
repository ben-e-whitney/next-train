import setuptools

setuptools.setup(
    name='next-train',
    version='1',
    author='Ben Whitney',
    author_email='ben.e.whitney@post.harvard.edu',
    url='https://github.com/ben-e-whitney/next-train',
    description=(
        'Script to parse a GTFS feed and '
        'find the next train between two stops.'
    ),
    license='GPLv3',
    python_requires='>=3.6',
    packages=setuptools.find_packages(),
    install_requires=['pyxdg'],
    entry_points={'console_scripts': ['next-train=next_train.main:main']},
    package_data={'next_train': ['*.csv']},
)
