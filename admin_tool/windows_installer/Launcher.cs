using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class Launcher
{
    // Quote each argument using Windows' CommandLineToArgvW/CRT conventions.
    private static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            result.Append(c);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string prefix = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
#if GUI
            string python = Path.Combine(prefix, "Scripts", "pythonw.exe");
            var arguments = new StringBuilder("-X utf8 -B -s -m yadof.tools.condor_gui");
#else
            string python = Path.Combine(prefix, "Scripts", "python.exe");
            var arguments = new StringBuilder("-X utf8 -B -s -m yadof");
#endif
            foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
            var start = new ProcessStartInfo(python, arguments.ToString());
            start.UseShellExecute = false;
            // These settings affect this child only; no machine/user environment is changed.
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
#if GUI
            start.CreateNoWindow = true;
#endif
            using (var child = Process.Start(start))
            {
                child.WaitForExit();
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
#if GUI
            System.Windows.Forms.MessageBox.Show(error.Message, "Yadof could not start");
#else
            Console.Error.WriteLine(error.Message);
#endif
            return 1;
        }
    }
}
