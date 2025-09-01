from setuptools import setup, find_packages

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='visiofirm',
    version='0.1.0',
    author='Safouane El Ghazouali', 
    author_email='safouane.elghazouali@gmail.com',
    description='Fast semi-automated image annotation tool for computer vision tasks detection, oriented bounding boxes and segmentation.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/OschAI/VisioFirm', 
    packages=find_packages(),
    py_modules=['run'],
    include_package_data=True,
    install_requires=[line.strip() for line in open('requirements.txt') if line.strip() and not line.startswith('#')],
    entry_points={
        'console_scripts': [
            'visiofirm = run:main',  
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache 2.0 License', 
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
)
