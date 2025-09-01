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
    install_requires=[
        'filelock==3.19.1',
        'Flask==3.1.2',
        'Flask_Login==0.6.3',
        'networkx==3.4.2',
        'openai_clip==1.0.1',
        'opencv_python==4.12.0.88',
        'Pillow==11.3.0',
        'psutil==7.0.0',
        'PyYAML==6.0.2',
        'rapidfuzz==3.13.0',
        'rarfile==4.2',
        'torch==2.8.0',
        'transformers==4.55.4',
        'ultralytics==8.3.185',
        'Werkzeug==3.1.3',
    ],
    entry_points={
        'console_scripts': [
            'visiofirm = run:main',  
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License', 
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
)