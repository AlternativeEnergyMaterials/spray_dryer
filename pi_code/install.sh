#!/bin/env bash
sudo apt update && sudo apt upgrade 
sudo apt install -y git libgpiod-dev socat
sudo nmcli c m "Wired connection 1" ipv4.method link-local

sudo apt install python3-pip 
pip install pi-plates --break-system-packages
pip install pyyaml --break-system-packages 
pip install sm16relind --break-system-packages 
pip install sm8mosind --break-system-packages 
pip install smtc --break-system-packages 

cd ~/ 
git clone https://github.com/SequentMicrosystems/8mosind-rpi.git 
cd ~/8mosind-rpi 
sudo make install

cd ~/ 
git clone https://github.com/SequentMicrosystems/16relind-rpi.git 
cd ~/16relind-rpi 
sudo make install 

cd ~/ 
git clone https://github.com/SequentMicrosystems/smtc-rpi.git 
cd ~/smtc-rpi 
sudo make install 

cd ~/ 
git clone https://github.com/SequentMicrosystems/SmartFan-rpi.git 
cd ~/SmartFan-rpi 
sudo make install 

cd ~/ 
mv picode/* ~/ 
rm –rf picode 

sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
