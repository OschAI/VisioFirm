from setuptools import setup, find_packages

def get_version():
    with open('visiofirm/__init__.py', 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip("'\"")
    raise RuntimeError('Unable to find version string in visiofirm/__init__.py')

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

# with open('requirements.txt', 'r', encoding='utf-8') as f:
#     install_requires = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='visiofirm',
    version=get_version(),
    author='Safouane El Ghazouali',
    author_email='safouane.elghazouali@gmail.com',
    description='Fast almost fully automated image annotation tool for computer vision tasks detection, oriented bounding boxes and segmentation.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/OschAI/VisioFirm',
    packages=find_packages(),
    py_modules=['run'],
    include_package_data=True,
    install_requires= [
        'filelock==3.19.1',
        'networkx==3.4.2',
        'openai_clip==1.0.1',
        'opencv-contrib-python==4.12.0.88',
        'Pillow==11.3.0',
        'psutil==7.0.0',
        'PyYAML==6.0.2',
        'rapidfuzz==3.13.0',
        'rarfile==4.2',
        'torch==2.8.0',
        'ultralytics==8.3.185',
        'Werkzeug==3.1.3',
        'groundingdino-py',
        'uvicorn==0.32.0',
        'waitress==3.0.2',
        'tqdm==4.67.1',
        'fastapi==0.115.0',
        'python-jose[cryptography]==3.3.0',
        'passlib[bcrypt]==1.7.4',
        'bcrypt==4.0.1',
        'python-multipart==0.0.20',
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