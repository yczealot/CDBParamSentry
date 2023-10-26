# author: cheng jiangdong

import configparser  # 导入configparser模块，用于解析INI文件
import subprocess  # 导入subprocess模块，用于执行系统命令
import mysql.connector  # 导入mysql.connector模块，用于连接MySQL数据库
import sys  # 导入sys模块，用于获取命令行参数
import re  # 导入re模块，用于正则表达式匹配

# 获取Linux系统设置的函数
def get_linux_setting(key,mountdir=None):
    try:
        # 执行sysctl命令获取系统设置
        if key == "ip_local_port_range":
            # 使用cat命令来获取ip_local_port_range的值
            result = subprocess.check_output(["cat", "/proc/sys/net/ipv4/ip_local_port_range"], universal_newlines=True)
        elif key == "scheduler":
            result = subprocess.check_output(["cat", "/sys/block/vdb/queue/scheduler"], universal_newlines=True)
            pattern = r"\[([^\]]+)\]"

            match = re.search(pattern, result)
            result = match.group(1) if match else None

        else:
            result = subprocess.check_output(["sysctl", "-n", key], universal_newlines=True)
        # 如果结果包含空格，例如范围值，将其转换为元组
        if " " in result:
            return tuple(map(str.strip, result.split()))
        # 截取前N个字符
        return result.strip()[:15]
    except:
        return None

# 获取MySQL数据库设置的函数
def get_mysql_setting(key, host='localhost', user='root', password='stayhungry', database=''):
    try:
        # 连接MySQL数据库
        cnx = mysql.connector.connect(user=user, password=password, host=host, database=database)
        cursor = cnx.cursor()
        # 执行SHOW VARIABLES命令获取MySQL设置
        query = f"SHOW VARIABLES LIKE '{key}';"
        cursor.execute(query)

        row = cursor.fetchone()
        if row:
            # 截取前10个字符
            return row[1][:10]
        return None
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'cnx' in locals():
            cnx.close()

# 获取挂载信息的函数
def get_mount_info(mountdir):
    try:
        # 执行mount命令获取挂载信息
        if "/" not in mountdir:
            mountdir = "/" + mountdir
        result = subprocess.check_output(["mount"], universal_newlines=True)
        for line in result.split("\n"):
            if mountdir in line:
                return line
        return None
    except:
        return None

# 获取设备调度器的函数
def get_scheduler(device):
    match = re.match(r"([a-zA-Z]+)", device)
    if match:
        device = match.group(1)
    with open(f"/sys/block/{device}/queue/scheduler", 'r') as f:
        scheduler = f.read().strip()
        match = re.search(r"\[(.*?)\]", scheduler)
        if match:
            scheduler = match.group(1)
    return scheduler

# 检查INI文件与系统设置是否一致的函数
def check_ini_against_system(ini_path, mountdir, isall=True):
    config = configparser.ConfigParser()
    config.read(ini_path)

    results = {}
    discrepancies = {}

    for section, section_content in config.items():
        for key, expected_value in section_content.items():
            if section == "System" and key not in ["mount", "filesystem", "scheduler"]:
                # 获取Linux系统设置
                actual_value = get_linux_setting(key)
                results[key] = {"expected": expected_value, "actual": actual_value}
                # 如果实际值与期望值不一致，记录差异
                if str(actual_value).lower() != str(expected_value).lower():
                    discrepancies[key] = {"expected": expected_value, "actual": actual_value}
            elif section == "Database":
                # 获取MySQL数据库设置
                actual_value = get_mysql_setting(key)
                results[key] = {"expected": expected_value, "actual": actual_value} 
                # 如果实际值与期望值不一致，记录差异
                if str(actual_value).lower() != str(expected_value).lower():
                    discrepancies[key] = {"expected": expected_value, "actual": actual_value}
            elif key in ["filesystem"] and mountdir:
                # 获取挂载信息
                mount_info = get_mount_info(mountdir)
                if mount_info:
                    # 正则表达式匹配挂载点和文件系统类型
                    match = re.search(r"on\s+(\S+)\s+type\s+(\S+)", mount_info)
                    if match:
                        mount_point, filesystem_type = match.groups()
                        #print("mount",mount_point,filesystem_type)
                        expected_filesystem = config.get("System", "filesystem", fallback="")
                        results[key] = {"expected": expected_filesystem, "actual": filesystem_type}                        
                        # 如果文件系统类型与期望值不一致，记录差异
                        if filesystem_type.lower() not in expected_filesystem.lower().split("|"):
                            discrepancies["filesystem"] = {"expected": expected_filesystem, "actual": filesystem_type}
            elif key in ["mount"] and mountdir:
                mount_info = get_mount_info(mountdir)
                mount_opts = re.search(r"\(([^)]+)\)", mount_info).group(1).split(',')
                expected_mount = config.get("System", "mount", fallback="").split(',')
                # 如果挂载选项与期望值不一致，记录差异
                missing_mount_opts = ["no " + opt for opt in expected_mount if opt not in mount_opts]
                results[key] =  {"expected": ",".join(expected_mount), "actual": ",".join(missing_mount_opts)} 
                if missing_mount_opts:
                    discrepancies["mount"] = {"expected": ",".join(expected_mount), "actual": ",".join(missing_mount_opts)}
            elif key in ["scheduler"] and mountdir:
                mount_info = get_mount_info(mountdir)
                device = mount_info.split()[0].split("/")[-1]
                # 获取设备调度器
                scheduler = get_scheduler(device)
                expected_scheduler = config.get("System", "scheduler", fallback="")
                results[key] = {"expected": expected_scheduler, "actual": scheduler}    
                # 如果设备调度器与期望值不一致，记录差异
                if scheduler and scheduler.lower() not in expected_scheduler.lower().split("|"):
                    discrepancies["scheduler"] = {"expected": expected_scheduler, "actual": scheduler}
            else:
                continue



    if isall:
        return results
    else:
        return discrepancies

# 打印检查结果的函数
def print_results(results, separator_length=40):
    header = "\033[32m{:<40} {:<40} {:<40}\033[0m".format("", "actual", "expected")
    print(header)
    for key, values in results.items():
        line = "{:<40} {:<40} {:<40}".format(key, str(values['actual']), str(values['expected']))
        print(line)

if __name__ == "__main__":
    ini_path = "Param.ini"
    isall = True
    mountdir = None

    if len(sys.argv) > 1:
        isall = sys.argv[1].lower() in ['1', 'true']
    if len(sys.argv) > 2:
        mountdir = sys.argv[2]
    separator_length = 50 if len(sys.argv) <= 3 else int(sys.argv[3])

    # 检查INI文件与系统设置是否一致
    print(f"Checking INI file: {ini_path} with mountdir: {mountdir} and isall set to: {isall}")
    results = check_ini_against_system(ini_path, mountdir, isall)
    # 打印检查结果
    print_results(results, separator_length)