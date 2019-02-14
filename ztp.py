from cli import configure, configurep, cli, pnp
from xml.dom import minidom
import re
import time

tftp_server = '192.168.0.1'

img_c9500="cat9k_iosxe.16.08.01a.SPA.bin"
img_c9500_md5="5a7ebf6cfc15b83125819b13feec25a9"
img_c9300="cat9k_iosxe.16.06.04a.SPA.bin"
img_c9300_md5="cee173ca374a8a388557c590eb3af680"
img_c3850="cat3k_caa-universalk9.16.06.04a.SPA.bin"
img_c3850_md5="a79564f834525edd3a2746235c64ab37"

c9500_version="Cisco IOS XE Software, Version 16.08.01a"
c9300_version="Cisco IOS XE Software, Version 16.06.04a"
c3850_version="Cisco IOS XE Software, Version 16.06.04a"

def get_serial():
    try:
        show_version = cli('show version')
    except pnp._pnp.PnPSocketError:
        time.sleep(90)
        show_version = cli('show version')
    try:
        serial = re.search(r"System Serial Number\s+:\s+(\S+)", show_version).group(1)
    except AttributeError:
        serial = re.search(r"Processor board ID\s+(\S+)", show_version).group(1)
    return serial

def get_platform():
    inventory = cli('show inventory | format')
    doc = minidom.parseString(inventory[1:])

    for node in doc.getElementsByTagName('InventoryEntry'):
        chassis = node.getElementsByTagName('ChassisName')[0]
        if "Chassis" in chassis.firstChild.data:
            platform = node.getElementsByTagName('PID')[0].firstChild.data
        elif "c95xx" in chassis.firstChild.data:
            platform = node.getElementsByTagName('PID')[0].firstChild.data
        elif "c93xx" in chassis.firstChild.data:
            platform = node.getElementsByTagName('PID')[0].firstChild.data
        elif "c38xx" in chassis.firstChild.data:
            platform = node.getElementsByTagName('PID')[0].firstChild.data

    return platform

def check_upgrade_required(model):
    time.sleep(5)
    sh_version = cli('show version | i Cisco IOS XE Software')
    sh_version = sh_version.strip(' \t\n\r')

    if 'C9500' in model:
        regex = "^" + c9500_version + "$"
        match = re.search(regex, sh_version)
        if match:
            print "\n\n*** No upgrade of Cat9500 software is required. ***\n\n"
        else:
            print "\n\n*** Upgrade of Cat9500 software is required. *** \n\n"
            upgrade_proceed(img_c9500, img_c9500_md5)

    elif 'C9300' in model:
        regex = "^" + c9300_version + "$"
        match = re.search(regex, sh_version)
        if match:
            print "\n\n*** No upgrade of Cat9300 software is required. ***\n\n"
        else:
            print "\n\n*** Upgrade of Cat9300 software is required. *** \n\n"
            upgrade_proceed(img_c9300, img_c9300_md5)

    elif 'C3850' in model:
        regex = "^" + c3850_version + "$"
        match = re.search(regex, sh_version)
        if match:
            print "\n\n*** No upgrade of Cat3850 software is required. ***\n\n"
        else:
            print "\n\n*** Upgrade of Cat3850 software is required. *** \n\n"
            upgrade_proceed(img_c3850, img_c3850_md5)

def deploy_eem_cleanup_script():
    install_command = 'install remove inactive'
    eem_commands = ['event manager applet cleanup',
                    'event none maxrun 600',
                    'action 1.0 cli command "enable"',
                    'action 2.0 cli command "%s" pattern "\[y\/n\]"' % install_command,
                    'action 2.1 cli command "y" pattern "proceed"',
                    'action 2.2 cli command "y"',
                    ]

    configure(eem_commands)

def deploy_eem_upgrade_script(image):
    install_command = 'install add file flash:' + image + ' activate commit'
    eem_commands = ['event manager applet upgrade',
                    'event none maxrun 600',
                    'action 1.0 cli command "enable"',
                    'action 2.0 cli command "%s" pattern "\[y\/n\/q\]"' % install_command,
                    'action 2.1 cli command "n" pattern "proceed"',
                    'action 2.2 cli command "y"'
                    ]

    configure(eem_commands)

def file_transfer(tftp_server, file, file_system='flash:/'):
    destination = file_system + file
    commands = ['file prompt quiet',
                'ip tftp blocksize 8192'
               ]

    configure(commands)

    transfer_file = "copy tftp://%s/%s %s" % (tftp_server, file, destination)
    transfer_results = cli(transfer_file)
    if 'OK' not in transfer_results:
        print "*** Failed file transfer ***" + str(transfer_results)

def verify_dst_image_md5(image, src_md5, file_system='flash:/'):
    verify_md5 = 'verify /md5 ' + file_system + image
    dst_md5 = cli(verify_md5)
    if src_md5 not in dst_md5:
        return False
    else:
        return True

def check_file_exists(file, file_system='flash:/'):
    dir_check = 'dir ' + file_system + file
    results = cli(dir_check)
    if 'No such file or directory' in results:
        return False
    elif 'Directory of %s%s' % (file_system, file) in results:
        return True
    else:
        print "Unexpected output from check_file_exists."
        output = results.split(':')[0]
        print "Output was: {}".format(output)

def configure_replace(file, file_system='flash:/'):
    config_command = 'copy %s%s running-config' % (file_system, file)
    cli(config_command)
    time.sleep(30)

def deploy_upgrade_script(image):
    deploy_eem_upgrade_script(image)
    print '*** Performing the upgrade. WARNING: DO NOT POWER OFF DEVICE. ***\n'
    cli('event manager run upgrade')
    time.sleep(600)

def upgrade_proceed(image, image_md5):
    if check_file_exists(image) is False:
        file_transfer(tftp_server, image)
        if verify_dst_image_md5(image, image_md5) is False:
            print '*** Image MD5 verification failed ***'
        else:
            deploy_upgrade_script(image)
    else:
        if verify_dst_image_md5(image, image_md5) is False:
            print '*** Image MD5 verification failed ***'
        else:
            deploy_upgrade_script(image)

def main():
    model = get_platform()

    print '\n\n*** STARTING ZTP SCRIPT ***'

    try:
        serial = get_serial()
    except Exception as GetSerialError:
        print "Error getting serial number: " + str(GetSerialError)
        pass

    config_file = "{}.cfg".format(serial)

    check_upgrade_required(model)

    if not check_file_exists(config_file):
        try:
            file_transfer(tftp_server, config_file)
            time.sleep(10)
        except Exception as TransferError:
            print "Configuration Transfer Error: " + str(TransferError)
            pass

    try:
        deploy_eem_cleanup_script()
        cli('event manager run cleanup')
        time.sleep(30)
    except Exception as DeployError:
        print "Error deploying cleanup script: " + str(DeployError)
        pass

    try:
        configure_replace(config_file)
    except Exception as ConfigError:
        print "Configuration Replace Error: " + str(ConfigError)
        pass

    configure('no event manager applet cleanup')

    print '\n\n*** FINISHED ZTP SCRIPT ***'

if __name__ == "__main__":
    main()
