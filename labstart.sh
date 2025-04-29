#!/bin/sh
# version 1.10 11-April 2024

# in theory it should work like this using Linux jason query "jq"
#lab_sku=`echo '{"username":"callb@vmware.com","tenant":"hol-test","lab":"HOL-8803-01"}' | jq '. | .lab' | sed s/\"//g`

# but what we get is this without the quotes so jq will not process
#vlp="{username:callb@vmware.com,tenant:hol-test,lab:HOL-8803-01}"

#furthermore the shell is not happy with the brackets and colons so unless the argument is quoted it doesn't work.
#therefore we have VLP Vm Script write the information in /tmp/vlpagent.txt at lab start (console open)
#Note: the lab console will not open if this script does not run to completion

# get the lab information from VLP
labstarttxt=/tmp/labstart.txt
cp $labstarttxt .

rawvlp=`cat $labstarttxt`

# DEBUG
#labstarttxt=labstart.txt

tenant=`cat $labstarttxt | cut -f2 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${tenant}" ] && tenant=""
student=`cat $labstarttxt | cut -f3 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${student}" ] || [ "${student}" = "unknown" ] && student=""
lab_sku=`cat $labstarttxt | cut -f4 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${lab_sku}" ] && lab_sku=""
#class=`cat $labstarttxt | cut -f5 -d ':' | cut -f1 -d',' | sed s/}//g`
#[ -z "${class}" ] && class=""
dp=`cat $labstarttxt | cut -f5 -d ':' | sed s/}//g`
[ -z "${dp}" ] && dp=""

vlp="${tenant}:${student}:${lab_sku}:${dp}"

#echo $vlp
#exit 0

# this file is created everytime the console opens
rm $labstarttxt

# /home/holuser/labstartup.sh creates the vPod_SKU.txt from the config.ini on the Main Console
vPod_SKU=`cat /tmp/vPod_SKU.txt`
holroot=/home/holuser/hol
lmcholroot=/lmchol/hol
wmcholroot=/wmchol/hol
LMC=false
WMC=false

# write the logs to the Main Console (LMC or WMC)
while true;do
   if [ -d ${lmcholroot} ];then
      logfile=${lmcholroot}/vmscript.log
      echo "LMC detected." >> ${logfile}
      mcholroot=${lmcholroot}
      desktopcfg='/lmchol/home/holuser/desktop-hol/VMware.config'
      LMC=true
      break
   elif [ -d ${wmcholroot} ];then
      logfile=${wmcholroot}/vmscript.log    
      echo "WMC detected." >> ${logfile}
      mcholroot=${wmcholroot}
      desktopcfg='/wmchol/DesktopInfo/desktopinfo.ini'
      WMC=true
      break
   fi
   sleep 5
done

echo "Running captain script for $vPod_SKU because lab $lab_sku is active." >> $logfile
echo "Here is the VLP lab start message: $rawvlp" >> $logfile

# update the desktop display if needed
if [ ! -z "${lab_sku}" ];then
   needed=`grep $lab_sku $desktopcfg`
else
   needed=`grep $vlp $desktopcfg`
fi

if [ -z "$needed" ];then
   #cat ${desktopcfg} | sed s/$vPod_SKU/$vlp/g > /tmp/desktop.config
   cat ${desktopcfg} | sed s/$vPod_SKU/$lab_sku/g > /tmp/desktop.config
   cp /tmp/desktop.config $desktopcfg
fi

# check and kill active labcheck processes
# remove labcheck at jobs
atrm $(atq | cut -f1)

# add lab sku specific commands here:



