# Copyright (C) 2013 Linaro Limited
#
# Author: Tyler Baker <tyler.baker@linaro.org>
#
# This file is part of LAVA Dispatcher.
#
# LAVA Dispatcher is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# LAVA Dispatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along
# with this program; if not, see <http://www.gnu.org/licenses>.

import logging
import contextlib
import time
import os
import subprocess
import pexpect

from lava_dispatcher.device.master import (
    MasterImageTarget
)
from lava_dispatcher.client.base import (
    NetworkCommandRunner,
)
from lava_dispatcher.utils import (
    string_to_list,
    mk_targz,
    rmtree,
    mkdtemp,
    extract_rootfs,
    ensure_directory,
)
from lava_dispatcher.errors import (
    CriticalError,
    OperationFailed,
)
from lava_dispatcher.downloader import (
    download_image,
)
from lava_dispatcher import deployment_data


class BootloaderTarget(MasterImageTarget):

    def __init__(self, context, config):
        super(BootloaderTarget, self).__init__(context, config)
        self._booted = False
        self._default_boot_cmds = 'boot_cmds_ramdisk'
        self._lava_nfsrootfs = None
        self._uboot_boot = False
        self._ipxe_boot = False
        self._uefi_boot = False
        self._boot_tags = {}
        self._base_tmpdir, self._tmpdir = self._setup_tmpdir()

    def _setup_tmpdir(self):
        if not self.config.use_lava_tmpdir:
            if self.config.alternative_dir is None:
                logging.error("You have specified not to use the LAVA temporary \
                              directory. However, you have not defined an \
                              alternate temporary directory. Falling back to \
                              use the LAVA temporary directory.")
                return self.context.config.lava_image_tmpdir, self.scratch_dir
            else:
                if self.config.alternative_create_tmpdir:
                    return self.config.alternative_dir, mkdtemp(self.config.alternative_dir)
                else:
                    return self.config.alternative_dir, self.config.alternative_dir
        else:
            return self.context.config.lava_image_tmpdir, self.scratch_dir

    def _get_rel_path(self, path):
        return os.path.relpath(path, self._base_tmpdir)

    def _get_http_url(self, path):
        prefix = self.context.config.lava_image_url
        return prefix + '/' + self._get_rel_path(path)

    def _is_uboot_ramdisk(self, ramdisk):
        try:
            out = subprocess.check_output('mkimage -l %s' % ramdisk, shell=True).splitlines()
        except subprocess.CalledProcessError:
            return False

        for line in out:
            if not line.startswith('Image Type:'):
                continue
            key, val = line.split(':')
            if val.find('RAMDisk') > 0:
                return True

        return False

    def _setup_nfs(self, nfsrootfs):
        self._lava_nfsrootfs = mkdtemp(basedir=self._tmpdir)
        extract_rootfs(nfsrootfs, self._lava_nfsrootfs)
        self._default_boot_cmds = 'boot_cmds_nfs'

    def _is_uboot(self):
        if self._uboot_boot:
            return True
        else:
            return False

    def _is_ipxe(self):
        if self._ipxe_boot:
            return True
        else:
            return False

    def _is_uefi(self):
        if self._uefi_boot:
            return True
        else:
            return False

    def _is_bootloader(self):
        if self._is_uboot() or self._is_ipxe() or self._is_uefi():
            return True
        else:
            return False

    def _set_boot_type(self, bootloadertype):
        if bootloadertype == "u_boot":
            self._uboot_boot = True
        elif bootloadertype == 'ipxe':
            self._ipxe_boot = True
        elif bootloadertype == 'uefi':
            self._uefi_boot = True
        else:
            raise CriticalError("Unknown bootloader type")

    def deploy_linaro_kernel(self, kernel, ramdisk, dtb, rootfs, nfsrootfs,
                             bootloader, firmware, rootfstype, bootloadertype,
                             target_type):
        # Get deployment data
        self.deployment_data = deployment_data.get(target_type)
        # We set the boot type
        self._set_boot_type(bootloadertype)
        # We are not booted yet
        self._booted = False
        # At a minimum we must have a kernel
        if kernel is None:
            raise CriticalError("No kernel image to boot")
        if self._is_uboot():
            # Set the server IP (Dispatcher)
            self._boot_tags['{SERVER_IP}'] = self.context.config.lava_server_ip
            # We have been passed kernel image
            kernel = download_image(kernel, self.context,
                                    self._tmpdir, decompress=False)
            self._boot_tags['{KERNEL}'] = self._get_rel_path(kernel)
            if ramdisk is not None:
                # We have been passed a ramdisk
                ramdisk = download_image(ramdisk, self.context,
                                         self._tmpdir,
                                         decompress=False)
                # Ensure ramdisk has u-boot header
                if not self._is_uboot_ramdisk(ramdisk):
                    ramdisk_uboot = ramdisk + ".uboot"
                    logging.info("RAMdisk needs u-boot header.  Adding.")
                    cmd = "mkimage -A arm -T ramdisk -C none -d %s %s > /dev/null" \
                        % (ramdisk, ramdisk_uboot)
                    r = subprocess.call(cmd, shell=True)
                    if r == 0:
                        ramdisk = ramdisk_uboot
                    else:
                        logging.warn("Unable to add u-boot header to ramdisk.  Tried %s" % cmd)
                self._boot_tags['{RAMDISK}'] = self._get_rel_path(ramdisk)
            if dtb is not None:
                # We have been passed a device tree blob
                dtb = download_image(dtb, self.context,
                                     self._tmpdir, decompress=False)
                self._boot_tags['{DTB}'] = self._get_rel_path(dtb)
            if rootfs is not None:
                # We have been passed a rootfs
                rootfs = download_image(rootfs, self.context,
                                        self._tmpdir, decompress=False)
                self._boot_tags['{ROOTFS}'] = self._get_rel_path(rootfs)
            if nfsrootfs is not None:
                # Extract rootfs into nfsrootfs directory
                nfsrootfs = download_image(nfsrootfs, self.context,
                                           self._tmpdir,
                                           decompress=False)
                self._setup_nfs(nfsrootfs)
                self._boot_tags['{NFSROOTFS}'] = self._lava_nfsrootfs
            if bootloader is not None:
                # We have been passed a bootloader
                bootloader = download_image(bootloader, self.context,
                                            self._tmpdir,
                                            decompress=False)
                self._boot_tags['{BOOTLOADER}'] = self._get_rel_path(bootloader)
            if firmware is not None:
                # We have been passed firmware
                firmware = download_image(firmware, self.context,
                                          self._tmpdir,
                                          decompress=False)
                self._boot_tags['{FIRMWARE}'] = self._get_rel_path(firmware)
        elif self._is_ipxe():
            # We have been passed kernel image
            kernel = download_image(kernel, self.context,
                                    self._tmpdir, decompress=False)
            kernel_url = self._get_http_url(kernel)
            self._boot_tags['{KERNEL}'] = kernel_url
            # We have been passed a ramdisk
            if ramdisk is not None:
                # We have been passed a ramdisk
                ramdisk = download_image(ramdisk, self.context,
                                         self._tmpdir,
                                         decompress=False)
                ramdisk_url = self._get_http_url(ramdisk)
                self._boot_tags['{RAMDISK}'] = ramdisk_url
            elif rootfs is not None:
                # We have been passed a rootfs
                rootfs = download_image(rootfs, self.context,
                                        self._tmpdir, decompress=False)
                rootfs_url = self._get_http_url(rootfs)
                self._boot_tags['{ROOTFS}'] = rootfs_url
        elif self._is_uefi():
            # Set the server IP (Dispatcher)
            self._boot_tags['{SERVER_IP}'] = self.context.config.lava_server_ip
            # We have been passed kernel image
            kernel = download_image(kernel, self.context,
                                    self._tmpdir, decompress=False)
            self._boot_tags['{KERNEL}'] = self._get_rel_path(kernel)
            if ramdisk is not None:
                # We have been passed a ramdisk
                ramdisk = download_image(ramdisk, self.context,
                                         self._tmpdir,
                                         decompress=False)
                self._boot_tags['{RAMDISK}'] = self._get_rel_path(ramdisk)
            if dtb is not None:
                # We have been passed a device tree blob
                dtb = download_image(dtb, self.context,
                                     self._tmpdir, decompress=False)
                self._boot_tags['{DTB}'] = self._get_rel_path(dtb)
            if rootfs is not None:
                # We have been passed a rootfs
                rootfs = download_image(rootfs, self.context,
                                        self._tmpdir, decompress=False)
                self._boot_tags['{ROOTFS}'] = self._get_rel_path(rootfs)
            if nfsrootfs is not None:
                # Extract rootfs into nfsrootfs directory
                nfsrootfs = download_image(nfsrootfs, self.context,
                                           self._tmpdir,
                                           decompress=False)
                self._setup_nfs(nfsrootfs)
                self._boot_tags['{NFSROOTFS}'] = self._lava_nfsrootfs
            if bootloader is not None:
                # We have been passed a bootloader
                bootloader = download_image(bootloader, self.context,
                                            self._tmpdir,
                                            decompress=False)
                self._boot_tags['{BOOTLOADER}'] = self._get_rel_path(bootloader)
            if firmware is not None:
                # We have been passed firmware
                firmware = download_image(firmware, self.context,
                                          self._tmpdir,
                                          decompress=False)
                self._boot_tags['{FIRMWARE}'] = self._get_rel_path(firmware)

    def deploy_linaro(self, hwpack, rfs, rootfstype, bootloadertype):
        self._uboot_boot = False
        super(BootloaderTarget, self).deploy_linaro(hwpack, rfs,
                                                    rootfstype, bootloadertype)

    def deploy_linaro_prebuilt(self, image, rootfstype, bootloadertype):
        self._uboot_boot = False
        if self._is_ipxe():
            if image is not None:
                self._ipxe_boot = True
                # We are not booted yet
                self._booted = False
                # We specify OE deployment data, vanilla as possible
                self.deployment_data = deployment_data.oe
                # We have been passed a image
                image = download_image(image, self.context,
                                       self._tmpdir,
                                       decompress=False)
                image_url = self._get_http_url(image)
                # We are booting an image, can be iso or whole disk
                self._boot_tags['{IMAGE}'] = image_url
            else:
                raise CriticalError("No image to boot")
        else:
            super(BootloaderTarget, self).deploy_linaro_prebuilt(image,
                                                                 rootfstype,
                                                                 bootloadertype)

    def _run_boot(self):
        self._enter_bootloader(self.proc)
        boot_cmds = self._load_boot_cmds(default=self._default_boot_cmds,
                                         boot_tags=self._boot_tags)
        # Sometimes a command must be run to clear u-boot console buffer
        if self.config.pre_boot_cmd:
            self.proc.sendline(self.config.pre_boot_cmd,
                               send_char=self.config.send_char)
        self._customize_bootloader(self.proc, boot_cmds)
        self.proc.expect(self.config.image_boot_msg, timeout=300)
        self._auto_login(self.proc)
        self._wait_for_prompt(self.proc, self.config.test_image_prompts,
                              self.config.boot_linaro_timeout)

    def _boot_linaro_image(self):
        if self._is_bootloader() and not self._booted:
            try:
                if self.config.hard_reset_command:
                    self._hard_reboot()
                    self._run_boot()
                else:
                    self._soft_reboot()
                    self._run_boot()
            except pexpect.TIMEOUT:
                raise OperationFailed("_run_boot failed:")
            # When the kernel does DHCP which is the case for NFS
            # the nameserver data does get populated by the DHCP
            # daemon. Thus, LAVA will populate the name server data.
            if self._lava_nfsrootfs:
                self.proc.sendline('cat /proc/net/pnp > /etc/resolv.conf',
                                   send_char=self.config.send_char)
            self.proc.sendline('export PS1="%s"'
                               % self.tester_ps1,
                               send_char=self.config.send_char)
            self._booted = True
        elif self._is_bootloader() and self._booted:
            self.proc.sendline('export PS1="%s"'
                               % self.tester_ps1,
                               send_char=self.config.send_char)
        else:
            super(BootloaderTarget, self)._boot_linaro_image()

    @contextlib.contextmanager
    def file_system(self, partition, directory):
        if self._is_bootloader() and not self._booted:
            self.power_on()
        if self._is_bootloader() and self._lava_nfsrootfs:
            path = '%s/%s' % (self._lava_nfsrootfs, directory)
            ensure_directory(path)
            yield path
        elif self._is_bootloader():
            try:
                pat = self.tester_ps1_pattern
                incrc = self.tester_ps1_includes_rc
                runner = NetworkCommandRunner(self, pat, incrc)

                targetdir = os.path.join('/', directory)
                runner.run('mkdir -p %s' % targetdir)
                parent_dir, target_name = os.path.split(targetdir)
                runner.run('/bin/tar -cmzf /tmp/fs.tgz -C %s %s'
                           % (parent_dir, target_name))
                runner.run('cd /tmp')  # need to be in same dir as fs.tgz

                ip = runner.get_target_ip()
                url_base = self._start_busybox_http_server(runner, ip)

                url = url_base + '/fs.tgz'
                logging.info("Fetching url: %s" % url)
                tf = download_image(url, self.context, self.scratch_dir,
                                    decompress=False)

                tfdir = os.path.join(self.scratch_dir, str(time.time()))

                try:
                    os.mkdir(tfdir)
                    self.context.run_command('/bin/tar -C %s -xzf %s'
                                             % (tfdir, tf))
                    yield os.path.join(tfdir, target_name)
                finally:
                    tf = os.path.join(self.scratch_dir, 'fs.tgz')
                    mk_targz(tf, tfdir)
                    rmtree(tfdir)

                    # get the last 2 parts of tf, ie "scratchdir/tf.tgz"
                    tf = '/'.join(tf.split('/')[-2:])
                    runner.run('rm -rf %s' % targetdir)
                    self._target_extract(runner, tf, parent_dir)
            finally:
                self._stop_busybox_http_server(runner)
        else:
            with super(BootloaderTarget, self).file_system(
                    partition, directory) as path:
                yield path

target_class = BootloaderTarget
