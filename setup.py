import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("VERSION", "r") as f:
    version = f.read()

setuptools.setup(
    name="firmware-helper",
    version="0.0.1",
    author="alphabet5",
    author_email="johnburt.jab@gmail.com",
    description="Copy credentials.",
    long_description="copy credentials",
    long_description_content_type="text/markdown",
    url="https://github.com/alphabet5/firmware-helper",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    entry_points={"console_scripts": ["fw=fw.fw:main"]},
    include_package_data=True,
    package_data={
        "fw": ["*"],
    },
    install_requires=["napalm", "joblib"],
)
