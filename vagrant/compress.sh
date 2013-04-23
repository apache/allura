#!/bin/bash

echo 'Cleanup bash history'
unset HISTFILE
[ -f /root/.bash_history ] && rm /root/.bash_history
[ -f /home/vagrant/.bash_history ] && rm /home/vagrant/.bash_history
 
echo 'Cleanup log files'
find /var/log -type f | while read f; do echo -ne '' > $f; done;
 
echo 'Whiteout root'
count=`df --sync -kP / | tail -n1  | awk -F ' ' '{print $4}'`; 
let count--
dd if=/dev/zero of=/tmp/whitespace bs=1024 count=$count;
rm /tmp/whitespace;
 
echo 'Whiteout /boot'
count=`df --sync -kP /boot | tail -n1 | awk -F ' ' '{print $4}'`;
let count--
dd if=/dev/zero of=/boot/whitespace bs=1024 count=$count;
rm /boot/whitespace;
