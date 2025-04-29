#!/bin/sh
# version 1.2 18-July 2024

# in theory it should work like this using Linux json query "jq"
#lab_sku=`echo '{"username":"callb@vmware.com","tenant":"hol-test","lab":"HOL-8803-01"}' | jq '. | .lab' | sed s/\"//g`

# but what we get is this without the quotes so jq will not process
#vlp="{username:callb@vmware.com,tenant:hol-test,lab:HOL-8803-01}"

#furthermore the shell is not happy with the brackets and colons so unless the argument is quoted it doesn't work.
#therefore we have VLP Vm Script write the information in /tmp/prepop.txt at prepop start

# this file is created when the prepop starts
# get the lab information from VLP
prepoptxt=/tmp/prepop.txt

# save in /home/holuser/prepop.txt in case review is needed
cp $prepoptxt /home/holuser/prepop.txt
rawvlp=`cat $prepoptxt`

tenant=`cat $prepoptxt | cut -f1 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${tenant}" ] && tenant=""
lab_sku=`cat $prepoptxt | cut -f2 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${lab_sku}" ] && lab_sku=""
student=`cat $prepoptxt | cut -f3 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${student}" ] || [ "${student}" = "unknown" ] && student=""
class=`cat $prepoptxt | cut -f4 -d ':' | cut -f1 -d',' | sed s/}//g`
[ -z "${class}" ] && class=""
dp=`cat $prepoptxt | cut -f5 -d ':' | sed s/}//g`
[ -z "${dp}" ] && dp=""

# this is the order of fields
vlp="${tenant}:${lab_sku}:${student}:${class}:${dp}"

# DEBUG
#echo $vlp
#exit 0

# remove the prepop.txt file so VLPagent.sh doesn't run again
rm $prepoptxt

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
      logfile=${lmcholroot}/skuactive.log
      echo "LMC detected." >> ${logfile}
      mcholroot=${lmcholroot}
      desktopcfg='/lmchol/home/holuser/desktop-hol/VMware.config'
      LMC=true
      break
   elif [ -d ${wmcholroot} ];then
      logfile=${wmcholroot}/skuactive.log    
      echo "WMC detected." >> ${logfile}
      mcholroot=${wmcholroot}
      desktopcfg='/wmchol/DesktopInfo/desktopinfo.ini'
      WMC=true
      break
   fi
   sleep 5
done

echo "Running $dp Deployment Pool script for $vPod_SKU at prepop start." >> $logfile
echo "Here is the full prepop message from VLP: $rawvlp" >> $logfile

# update the desktop display if needed
# probably leave desktop display update to labstart.sh instead
#if [ ! -z "${lab_sku}" ];then
#   needed=`grep $lab_sku $desktopcfg`
#else
#   needed=`grep $vlp $desktopcfg`
#fi

#if [ -z "$needed" ];then
#   cat ${desktopcfg} | sed s/$vPod_SKU/${vlp}/g > /tmp/desktop.config
#   cp /tmp/desktop.config $desktopcfg
#fi

# add deployment pool specific commands here:

# EXAMPLE:
#if [ "${dp}" = "HOL-2531-perf-vmworld" ];then
#	if [ -f /vpodrepo/2025-labs/2531/autolab.py ];then
#		echo "Starting autolab.py" >> $logfile
#		python3 /vpodrepo/2025-labs/2531/autolab.py
#	else
#		echo "The autolab.py script is not present." >> $logfile
#	fi
#fi
