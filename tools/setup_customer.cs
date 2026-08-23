using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

static class SetupCustomer
{
    [STAThread]
    static int Main()
    {
        string appName = "个人财务软件客户版";
        string exeName = "财务软件客户版.exe";
        string dest = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs",
            appName
        );
        try
        {
            Directory.CreateDirectory(dest);
            string tempZip = Path.Combine(Path.GetTempPath(), "finance_customer_setup", "customer.zip");
            Directory.CreateDirectory(Path.GetDirectoryName(tempZip));
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("customer.zip"))
            using (FileStream output = File.Create(tempZip))
            {
                resource.CopyTo(output);
            }
            string command = string.Format(
                "Expand-Archive -Path '{0}' -DestinationPath '{1}' -Force",
                tempZip.Replace("'", "''"),
                dest.Replace("'", "''")
            );
            Process.Start(
                "powershell.exe",
                "-NoProfile -ExecutionPolicy Bypass -Command \"" + command + "\""
            ).WaitForExit();
            File.Delete(tempZip);

            string exe = Path.Combine(dest, exeName);
            if (File.Exists(exe))
            {
                CreateShortcut(exe, dest);
                Process.Start(exe);
            }
            MessageBox.Show(
                appName + " 安装完成，桌面已创建快捷方式。",
                "安装完成",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information
            );
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "安装失败：" + ex.Message,
                "安装错误",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }

    static void CreateShortcut(string exePath, string workingDir)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string shortcutPath = Path.Combine(desktop, "个人财务软件客户版.lnk");
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember(
            "CreateShortcut",
            BindingFlags.InvokeMethod,
            null,
            shell,
            new object[] { shortcutPath }
        );
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember(
            "TargetPath",
            BindingFlags.SetProperty,
            null,
            shortcut,
            new object[] { exePath }
        );
        shortcutType.InvokeMember(
            "WorkingDirectory",
            BindingFlags.SetProperty,
            null,
            shortcut,
            new object[] { workingDir }
        );
        shortcutType.InvokeMember(
            "Save",
            BindingFlags.InvokeMethod,
            null,
            shortcut,
            null
        );
    }
}
