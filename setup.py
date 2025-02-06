from setuptools import setup, find_packages

setup(
    name="AI Financial Engineering Agentic System",
    version="0.1.0",
    author="Amit Lal",
    author_email="amitlal@example.com",
    description="An AI-based financial engineering system for analyzing and predicting financial markets.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/amitlals/AI-Financial-Engineering-Agentic-System",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        "numpy==1.21.0",
        "pandas==1.3.0",
        "scikit-learn==0.24.2",
        "tensorflow==2.5.0",
        "matplotlib==3.4.2",
        "seaborn==0.11.1",
    ],
    entry_points={
        "console_scripts": [
            "ai-financial-engineering=main:main",
        ],
    },
)
