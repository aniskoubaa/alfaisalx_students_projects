// TurtleBotConnect.cs - one-click SSH helper for the lab TurtleBot 4 (Windows).
//
// It automates the steps in TurtleBot/HOW-TO-CONNECT.md: find the robot, open a terminal on it,
// set up key login, read its status, stop the motion programs, copy a file, add an SSH config
// shortcut and fix a changed host key. It runs the OpenSSH client that ships with Windows
// (ssh.exe, ssh-keygen.exe, scp.exe) in this console window.
//
// Security: it never stores, reads or passes a password. ssh asks for passwords itself. Every ssh and scp
// call checks the robot against the host key built into this file (PinnedHostKeyDefault), so a device
// that is not the robot is refused before a password prompt appears.
// Files it writes: %APPDATA%\TurtleBotConnect\last_host.txt and known_hosts (the pinned key), your key
// (option 3) and, only if you choose option 6, a block appended to %USERPROFILE%\.ssh\config (backup first).
//
// Build: run build.cmd in this folder. It uses the C# 5 compiler that ships with Windows
// (.NET Framework 4.x), so this file must stay C# 5: no $"", ?., nameof, tuples or => members.
// macOS and Linux: use connect-turtlebot.sh in the same folder.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

[assembly: AssemblyTitle("TurtleBot Connect")]
[assembly: AssemblyDescription("Opens a terminal on the lab TurtleBot 4 over SSH")]
[assembly: AssemblyProduct("TurtleBot Connect")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

namespace TurtleBotConnect
{
    internal sealed class Probe
    {
        public string Host;
        public string Label;
        public bool Done;
        public bool Ok;
        public string Address;
        public string Note;
    }

    internal static class Program
    {
        const string Version = "1.1.0";
        const string DefaultUser = "ubuntu";
        const string MdnsName = "turtlebot4.local";
        const string ApAddress = "10.42.0.1";
        const string AliasName = "turtlebot4";
        const string Guide = "TurtleBot/HOW-TO-CONNECT.md";
        const int SshPort = 22;
        const int ProbeTimeoutMs = 2500;
        const int SearchDeadlineMs = 5500;

        const int ExitOk = 0;
        const int ExitNotFound = 1;
        const int ExitUsage = 2;

        // The lab robot's SSH host key. It is public (not a secret). Every ssh and scp call made by this program
        // accepts only this key, under the name PinAlias, from a known_hosts file the program writes itself.
        // The maintainer reads it on the robot with  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
        // (fingerprint SHA256:P2rMsKzoIV+vsYEUViVNEFf9H8ORHn+qYbEhaTciyi4, checked on 2026-10-04).
        // After the robot is reinstalled: update this line and PINNED_HOST_KEY in connect-turtlebot.sh,
        // run build.cmd, and update the fingerprint in README.md and HOW-TO-CONNECT.md.
        const string PinnedHostKeyDefault = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINezwwah6HhR6o0ONkI77+B+XmFckK7JhQHI1Fn1nyBb";
        const string PinAlias = "turtlebot4-lab";

        // Read-only status script run on the robot. It must not contain double quotes, so that it can be
        // passed as one double-quoted argument on the Windows command line. Keep it identical to
        // STATUS_SCRIPT in connect-turtlebot.sh.
        const string StatusScript =
            "echo '== Robot =='; echo Name: $(hostname), $(uptime -p); " +
            "echo '== Wi-Fi address (wlan0) =='; ip -4 -br addr show wlan0 2>/dev/null || echo 'wlan0 not found'; " +
            "echo '== Robot software and lidar =='; s=$(systemctl is-active turtlebot4.service 2>/dev/null); " +
            "case $s in active) echo 'turtlebot4.service: running';; *) echo turtlebot4.service: NOT running, state: $s;; esac; " +
            "if [ -e /dev/RPLIDAR ]; then echo 'Lidar USB (/dev/RPLIDAR): connected'; " +
            "else echo 'Lidar USB (/dev/RPLIDAR): NOT found (check the lidar USB cable)'; fi; " +
            "echo '== Battery and dock (asking ROS, this can take up to a minute) =='; " +
            "source /etc/turtlebot4/setup.bash >/dev/null 2>&1; t=$(mktemp -d); " +
            "timeout 45 ros2 topic echo --once /battery_state --field percentage >$t/b 2>/dev/null & " +
            "timeout 45 ros2 topic echo --once /dock_status --field is_docked >$t/d 2>/dev/null & " +
            "wait; b=$(head -n 1 $t/b); d=$(head -n 1 $t/d); rm -rf $t; " +
            "case $b in '') echo 'Battery: no answer within 45 s';; " +
            "*) echo Battery: $(echo $b | awk '{v=$1; if (v<=1) v=v*100; print int(v+0.5)}') %;; esac; " +
            "case $d in True) echo 'Docked: yes (on the charging dock)';; False) echo 'Docked: no (off the dock)';; " +
            "'') echo 'Docked: no answer within 45 s';; *) echo Docked: $d;; esac; " +
            "case $b$d in '') echo 'ROS did not answer. If the robot started less than 2 minutes ago, wait and try again. " +
            "Otherwise the Create 3 base may be stuck: see HOW-TO-CONNECT.md, Restart the Create 3 base application.';; esac";

        // Emergency stop run on the robot. The [x] in each pattern matches the same programs as the plain
        // name, but stops pkill -f from matching (and killing) the remote shell that runs this command,
        // whose own command line contains the patterns. Keep it identical to STOP_COMMAND in the .sh.
        const string StopCommand =
            "touch ~/STOP; pkill -INT -f 'motion_shape[s].py'; pkill -INT -f 'more_shape[s].py'; " +
            "pkill -INT -f 'wall_approac[h].py'; pkill -INT -f 'keep_distanc[e].py'; pkill -TERM -f 'campaig[n].sh'; " +
            "pkill -INT -f 'ros2 action send_goa[l]'; echo STOP-SENT";

        static readonly Regex HostRegex = new Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{0,252}$");
        static readonly Regex UserRegex = new Regex("^[A-Za-z_][A-Za-z0-9_.-]{0,31}$");
        static readonly Regex Base64Regex = new Regex("^[A-Za-z0-9+/]{20,}={0,2}$");

        static string user = DefaultUser;
        static string keyPath;
        static string sshConfigPath;
        static string knownHostsPath;
        static string pinnedHostKey = PinnedHostKeyDefault;
        static bool trustNewHostKey;
        static string currentHost;
        static bool currentHostVerified;
        static bool menuMode;
        static string sshExe;
        static string sshKeygenExe;
        static string scpExe;
        static volatile bool childRunning;

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint GetConsoleProcessList(uint[] processList, uint processCount);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr GetStdHandle(int nStdHandle);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);

        // ------------------------------------------------------------------ entry point

        static int Main(string[] args)
        {
            Console.CancelKeyPress += OnCancelKeyPress;
            try
            {
                return Run(args);
            }
            catch (Exception ex)
            {
                Fail("Unexpected problem: " + ex.Message);
                if (menuMode) PauseIfOwnConsole();
                return ExitUsage;
            }
        }

        static void OnCancelKeyPress(object sender, ConsoleCancelEventArgs e)
        {
            // While ssh runs, Ctrl+C belongs to ssh: keep this program (and its menu) alive.
            if (childRunning) e.Cancel = true;
        }

        static int Run(string[] args)
        {
            keyPath = DefaultKeyPath();
            sshConfigPath = Path.Combine(Path.Combine(UserProfile(), ".ssh"), "config");
            string optHost = null;
            List<string> positional = new List<string>();

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                string lower = a.ToLowerInvariant();
                if (lower == "--help" || lower == "-h" || lower == "/?" || lower == "help")
                {
                    PrintHelp();
                    return ExitOk;
                }
                if (lower == "--version" || lower == "-v")
                {
                    Console.WriteLine("TurtleBotConnect " + Version);
                    return ExitOk;
                }
                if (lower == "--trust-new-host-key")
                {
                    trustNewHostKey = true;
                    continue;
                }
                if (lower == "--host" || lower == "--user" || lower == "--key" || lower == "--ssh-config" || lower == "--known-hosts" ||
                    lower == "--pinned-key")
                {
                    if (i + 1 >= args.Length) return Usage("Missing value after " + a + ".");
                    string v = args[++i];
                    if (lower == "--host")
                    {
                        optHost = NormalizeHost(v);
                        if (optHost == null) return Usage("Not a valid robot name or address: " + v);
                    }
                    else if (lower == "--user")
                    {
                        if (!UserRegex.IsMatch(v)) return Usage("Not a valid user name: " + v);
                        user = v;
                    }
                    else if (lower == "--key")
                    {
                        keyPath = Path.GetFullPath(StripQuotes(v));
                    }
                    else if (lower == "--ssh-config")
                    {
                        sshConfigPath = Path.GetFullPath(StripQuotes(v)); // hidden: for testing
                    }
                    else if (lower == "--known-hosts")
                    {
                        knownHostsPath = Path.GetFullPath(StripQuotes(v)); // hidden: for testing
                    }
                    else
                    {
                        // hidden: pin another server's key, for testing against a test SSH server
                        string[] parts = StripQuotes(v).Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                        if (parts.Length < 2 || parts[0] != "ssh-ed25519" || !Base64Regex.IsMatch(parts[1]))
                            return Usage("--pinned-key needs \"ssh-ed25519 <base64>\".");
                        pinnedHostKey = parts[0] + " " + parts[1];
                    }
                    continue;
                }
                if (a.StartsWith("-")) return Usage("Unknown option: " + a);
                positional.Add(a);
            }

            if (trustNewHostKey && !(positional.Count > 0 && positional[0].ToLowerInvariant() == "find"))
                PrintTrustNewWarning();

            if (positional.Count == 0)
            {
                menuMode = true;
                if (optHost != null)
                {
                    currentHost = optHost;
                    currentHostVerified = false;
                }
                return Menu();
            }

            string command = positional[0].ToLowerInvariant();
            if (positional.Count > 2) return Usage("Too many arguments.");
            string hostArg = optHost;
            if (positional.Count == 2)
            {
                if (command == "find") return Usage("find takes no address; use --host <address> to test one address.");
                hostArg = NormalizeHost(positional[1]);
                if (hostArg == null) return Usage("Not a valid robot name or address: " + positional[1]);
            }

            switch (command)
            {
                case "find":
                    return DoFind(hostArg);
                case "connect":
                    if (!RequireSsh()) return ExitUsage;
                    return DoConnect(hostArg, false);
                case "status":
                    if (!RequireSsh()) return ExitUsage;
                    return DoStatus(hostArg, false);
                case "stop":
                    if (!RequireSsh()) return ExitUsage;
                    return DoStop(hostArg, false);
                case "setup-key":
                    if (!RequireSsh()) return ExitUsage;
                    return DoSetupKey(hostArg, false);
                default:
                    return Usage("Unknown command: " + positional[0]);
            }
        }

        static int Usage(string message)
        {
            Fail(message);
            Info("Run  TurtleBotConnect.exe --help  for the list of commands.");
            return ExitUsage;
        }

        static void PrintHelp()
        {
            Console.WriteLine("TurtleBot Connect " + Version + " - open a terminal on the lab TurtleBot 4 over SSH.");
            Console.WriteLine();
            Console.WriteLine("Usage:");
            Console.WriteLine("  TurtleBotConnect.exe                    menu (double-clicking the program starts this)");
            Console.WriteLine("  TurtleBotConnect.exe connect [host]     find the robot and open a terminal on it");
            Console.WriteLine("  TurtleBotConnect.exe find               look for the robot and print its address");
            Console.WriteLine("  TurtleBotConnect.exe status [host]      print the robot's status (read only, up to a minute)");
            Console.WriteLine("  TurtleBotConnect.exe stop [host]        EMERGENCY: stop the motion programs on the robot");
            Console.WriteLine("  TurtleBotConnect.exe setup-key [host]   create your key and install it on the robot (one time)");
            Console.WriteLine();
            Console.WriteLine("Options:");
            Console.WriteLine("  --host <address>   robot name or address. Without it the program tries the last address");
            Console.WriteLine("                     that worked, then " + MdnsName + ", then " + ApAddress + ".");
            Console.WriteLine("  --user <name>      login name on the robot (default: " + DefaultUser + ")");
            Console.WriteLine("  --key <path>       private key file (default: " + DefaultKeyPath() + ")");
            Console.WriteLine("  --trust-new-host-key");
            Console.WriteLine("                     do not check the robot against the host key built into this program;");
            Console.WriteLine("                     ssh asks instead. Only after the lab maintainer confirms the robot was");
            Console.WriteLine("                     reinstalled and this program has not been updated yet.");
            Console.WriteLine("  --help             show this text");
            Console.WriteLine("  --version          show the version");
            Console.WriteLine();
            Console.WriteLine("Exit codes: 0 OK, 1 robot not found, 2 ssh missing or usage error, other: exit code of ssh.");
            Console.WriteLine("The robot must present the SSH host key built into this program, fingerprint");
            Console.WriteLine("  " + PinnedFingerprint() + ";");
            Console.WriteLine("any other device is refused before a password prompt appears.");
            Console.WriteLine("Passwords are never stored: ssh asks for them itself. Full guide: " + Guide);
        }

        // ------------------------------------------------------------------ menu

        static int Menu()
        {
            try { Console.Title = "TurtleBot Connect"; } catch { }
            if (!LocateSsh())
            {
                PrintSshMissing();
                PauseIfOwnConsole();
                return ExitUsage;
            }
            while (true)
            {
                PrintMenu();
                string choice = Prompt("Choose a number and press Enter: ");
                if (choice == null) return ExitOk; // end of input
                choice = choice.ToLowerInvariant();
                if (choice == "0" || choice == "q" || choice == "exit") return ExitOk;
                try
                {
                    switch (choice)
                    {
                        case "1": DoConnect(null, true); break;
                        case "2": MenuFind(); break;
                        case "3": DoSetupKey(null, true); break;
                        case "4": DoStatus(null, true); break;
                        case "5": DoVsCode(); break;
                        case "6": DoSshConfig(); break;
                        case "7": DoStop(null, true); break;
                        case "8": DoCopy(); break;
                        case "9": DoFixHostKey(); break;
                        default:
                            Warn("Please type a number from 0 to 9.");
                            continue;
                    }
                }
                catch (Exception ex)
                {
                    // One failed action (for example an unwritable file) must not close the menu.
                    Fail("Problem: " + ex.Message);
                }
                if (!Console.IsInputRedirected)
                {
                    if (Prompt("Press Enter to return to the menu...") == null) return ExitOk;
                }
            }
        }

        static void PrintMenu()
        {
            Console.WriteLine();
            Head("====================================================");
            Head("  TurtleBot Connect " + Version + "   (lab TurtleBot 4)");
            Head("====================================================");
            string robot;
            if (currentHost == null) robot = "not searched yet (option 1 or 2 finds it)";
            else robot = currentHost + (currentHostVerified ? "  (answered)" : "  (not checked yet)");
            Info("  Robot:  " + robot);
            Info("  Key:    " + (File.Exists(keyPath) ? keyPath : "none yet (option 3 lets you log in without the password)"));
            if (trustNewHostKey)
                Warn("  Robot identity: NOT checked (--trust-new-host-key). Compare fingerprints with the lab maintainer.");
            else
                Info("  Robot identity: checked against the built-in host key (" + PinnedFingerprint() + ")");
            Console.WriteLine();
            Say("  1) Connect (open a robot terminal)", ConsoleColor.White);
            Say("  2) Find the robot", ConsoleColor.White);
            Say("  3) Set up key login (one time)", ConsoleColor.White);
            Say("  4) Robot status (read only)", ConsoleColor.White);
            Say("  5) Open in VS Code", ConsoleColor.White);
            Say("  6) Add a 'turtlebot4' shortcut to my SSH config", ConsoleColor.White);
            Say("  7) EMERGENCY: stop motion programs", ConsoleColor.Red);
            Say("  8) Copy a file to the robot", ConsoleColor.White);
            Say("  9) Fix \"host key changed\"", ConsoleColor.White);
            Say("  0) Exit", ConsoleColor.White);
            Console.WriteLine();
        }

        // ------------------------------------------------------------------ finding the robot

        static int DoFind(string hostArg)
        {
            bool found;
            if (hostArg != null) found = ProbeSingle(hostArg);
            else found = SearchRobot();
            if (!found)
            {
                PrintNotFound(false);
                return ExitNotFound;
            }
            Good("Robot found: " + currentHost);
            Info("Open a terminal on it:  TurtleBotConnect.exe connect   (or: ssh " + user + "@" + currentHost + ")");
            return ExitOk;
        }

        static void MenuFind()
        {
            currentHost = null;
            currentHostVerified = false;
            if (SearchRobot())
            {
                Good("Robot found: " + currentHost + ". Choose 1 to open a terminal on it.");
                return;
            }
            PrintNotFound(true);
            string h = AskForAddress();
            if (h != null) Good("Robot found: " + h + ". Choose 1 to open a terminal on it.");
        }

        // Returns the host to use, or null when the robot cannot be reached.
        static string ResolveHost(string hostArg, bool interactive)
        {
            if (hostArg != null)
            {
                if (ProbeSingle(hostArg)) return hostArg;
                PrintNotFound(interactive);
                return interactive ? AskForAddress() : null;
            }
            if (currentHost != null)
            {
                if (currentHostVerified) return currentHost;
                if (ProbeSingle(currentHost)) return currentHost;
                Warn("No answer from " + currentHost + "; searching the usual addresses instead.");
                currentHost = null;
            }
            if (SearchRobot()) return currentHost;
            PrintNotFound(interactive);
            return interactive ? AskForAddress() : null;
        }

        static bool SearchRobot()
        {
            List<string> hosts = new List<string>();
            List<string> labels = new List<string>();
            string last = LoadLastHost();
            if (last != null)
            {
                hosts.Add(last);
                labels.Add(last + " (last used)");
            }
            foreach (string h in new string[] { MdnsName, ApAddress })
            {
                bool dup = false;
                foreach (string x in hosts) if (string.Equals(x, h, StringComparison.OrdinalIgnoreCase)) dup = true;
                if (!dup)
                {
                    hosts.Add(h);
                    labels.Add(h);
                }
            }
            Info("Looking for the robot (this takes up to 6 seconds)...");
            Probe winner = Search(hosts, labels);
            if (winner == null) return false;
            SetCurrent(winner.Host);
            return true;
        }

        static bool ProbeSingle(string host)
        {
            Info("Checking " + host + " ...");
            Probe winner = Search(new List<string> { host }, new List<string> { host });
            if (winner == null) return false;
            SetCurrent(host);
            return true;
        }

        static void SetCurrent(string host)
        {
            currentHost = host;
            currentHostVerified = true;
            SaveLastHost(host);
        }

        // Probes all hosts in parallel; returns the first host in list order whose SSH port answered.
        static Probe Search(List<string> hosts, List<string> labels)
        {
            List<Probe> probes = new List<Probe>();
            for (int i = 0; i < hosts.Count; i++)
            {
                Probe p = new Probe();
                p.Host = hosts[i];
                p.Label = labels[i];
                probes.Add(p);
                Probe captured = p;
                Thread t = new Thread(delegate() { RunProbe(captured); });
                t.IsBackground = true;
                t.Start();
            }
            Stopwatch sw = Stopwatch.StartNew();
            Probe winner = null;
            while (true)
            {
                bool timedOut = sw.ElapsedMilliseconds >= SearchDeadlineMs;
                bool waiting = false;
                winner = null;
                foreach (Probe p in probes)
                {
                    bool done, ok;
                    lock (p) { done = p.Done; ok = p.Ok; }
                    if (done && ok) { winner = p; break; }
                    if (!done && !timedOut) { waiting = true; break; }
                }
                if (winner != null || !waiting) break;
                Thread.Sleep(50);
            }
            foreach (Probe p in probes)
            {
                bool done, ok;
                string note, address;
                lock (p) { done = p.Done; ok = p.Ok; note = p.Note; address = p.Address; }
                string label = "  " + p.Label.PadRight(32);
                if (p == winner) Good(label + "answered (SSH at " + address + ")");
                else if (done && !ok) Info(label + note);
                else if (winner != null) Info(label + "not needed");
                else Info(label + "no answer in time");
            }
            return winner;
        }

        static void RunProbe(Probe p)
        {
            bool ok = false;
            string address = null;
            string note = null;
            try
            {
                IPAddress[] all = Dns.GetHostAddresses(p.Host);
                List<IPAddress> ordered = new List<IPAddress>();
                foreach (IPAddress a in all) if (a.AddressFamily == AddressFamily.InterNetwork) ordered.Add(a);
                foreach (IPAddress a in all) if (a.AddressFamily == AddressFamily.InterNetworkV6) ordered.Add(a);
                if (ordered.Count == 0)
                {
                    note = "name not found";
                }
                else
                {
                    for (int i = 0; i < ordered.Count && i < 2 && !ok; i++)
                    {
                        if (TcpPortOpen(ordered[i], SshPort, ProbeTimeoutMs))
                        {
                            ok = true;
                            address = ordered[i].ToString();
                        }
                    }
                    if (!ok) note = "no answer (address " + ordered[0] + ")";
                }
            }
            catch (SocketException)
            {
                note = "name not found";
            }
            catch (Exception ex)
            {
                note = "error: " + ex.Message;
            }
            lock (p)
            {
                p.Ok = ok;
                p.Address = address;
                p.Note = note;
                p.Done = true;
            }
        }

        // Probes one host without printing anything; gives up after about 4 seconds.
        static bool QuickProbe(string host)
        {
            Probe p = new Probe();
            p.Host = host;
            p.Label = host;
            Thread t = new Thread(delegate() { RunProbe(p); });
            t.IsBackground = true;
            t.Start();
            if (!t.Join(ProbeTimeoutMs + 1500)) return false;
            lock (p) { return p.Ok; }
        }

        static bool TcpPortOpen(IPAddress ip, int port, int timeoutMs)
        {
            try
            {
                using (Socket s = new Socket(ip.AddressFamily, SocketType.Stream, ProtocolType.Tcp))
                {
                    IAsyncResult ar = s.BeginConnect(ip, port, null, null);
                    if (!ar.AsyncWaitHandle.WaitOne(timeoutMs)) return false;
                    s.EndConnect(ar);
                    return s.Connected;
                }
            }
            catch
            {
                return false;
            }
        }

        static void PrintNotFound(bool interactive)
        {
            Fail("The robot did not answer.");
            Info("This computer's network addresses (IPv4):");
            List<string> mine = LocalIPv4();
            bool onRobotWifi = false;
            if (mine.Count == 0) Info("  none: this computer is not connected to a network");
            foreach (string line in mine)
            {
                Info("  " + line);
                if (line.Contains(": 10.42.0.")) onRobotWifi = true;
            }
            if (onRobotWifi)
            {
                Warn("You are on the robot's own Wi-Fi (10.42.0.x), but 10.42.0.1 did not answer.");
                Warn("The robot may still be starting: wait about 2 minutes after the chime and try again.");
            }
            Info("What to do:");
            Info("  1. Check that the robot sits on its dock and is on. After it starts, wait about 2 minutes:");
            Info("     it plays a chime and shows its address on the display.");
            Info("  2. Display shows 10.87.x.x: join the 'Students' Wi-Fi on this computer, then try again");
            Info("     (the program uses the name " + MdnsName + ").");
            Info("  3. Display shows 10.42.0.1: join the robot's own Wi-Fi 'Turtlebot4' (it has no internet),");
            Info("     then try again.");
            if (interactive) Info("  4. Otherwise type the address shown on the robot's display below.");
            else Info("  4. Otherwise give the address from the display, for example:  TurtleBotConnect.exe connect 10.87.10.205");
            Info("  More help: " + Guide + ", section Troubleshooting.");
        }

        static string AskForAddress()
        {
            while (true)
            {
                string s = Prompt("Type the robot's address from its display (or press Enter to go back): ");
                if (string.IsNullOrEmpty(s)) return null;
                string h = NormalizeHost(s);
                if (h == null)
                {
                    Warn("That does not look like an address. Example: 10.87.10.205");
                    continue;
                }
                if (ProbeSingle(h)) return h;
                Warn("No answer from " + h + ". Check the address on the display, and that this computer is on the same Wi-Fi.");
            }
        }

        static List<string> LocalIPv4()
        {
            List<string> result = new List<string>();
            try
            {
                foreach (NetworkInterface ni in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (ni.OperationalStatus != OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
                    foreach (UnicastIPAddressInformation u in ni.GetIPProperties().UnicastAddresses)
                    {
                        if (u.Address.AddressFamily != AddressFamily.InterNetwork) continue;
                        string a = u.Address.ToString();
                        string extra = a.StartsWith("169.254.") ? "  (no address given by the network)" : "";
                        result.Add(ni.Name + ": " + a + extra);
                    }
                }
            }
            catch
            {
                // Listing addresses is only a hint; ignore failures.
            }
            return result;
        }

        static string StateDir()
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "TurtleBotConnect");
        }

        static string StatePath()
        {
            return Path.Combine(StateDir(), "last_host.txt");
        }

        static string PinnedKnownHostsPath()
        {
            return Path.Combine(StateDir(), "known_hosts");
        }

        static string LoadLastHost()
        {
            try
            {
                string path = StatePath();
                if (!File.Exists(path)) return null;
                string s = File.ReadAllText(path).Trim();
                return HostRegex.IsMatch(s) ? s : null;
            }
            catch
            {
                return null;
            }
        }

        static void SaveLastHost(string host)
        {
            try
            {
                string path = StatePath();
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllText(path, host + Environment.NewLine);
            }
            catch
            {
                // Remembering the address is a convenience only.
            }
        }

        // ------------------------------------------------------------------ 1) connect

        static int DoConnect(string hostArg, bool interactive)
        {
            string host = ResolveHost(hostArg, interactive);
            if (host == null) return ExitNotFound;
            string target = user + "@" + host;
            string args = "-t " + SshOptions() + KeyOption() + " " + Q(target);
            Good("Opening a terminal on the robot (" + target + ").");
            Info("Type  exit  (or press Ctrl+D) to log out" + (menuMode ? " and come back to this menu." : "."));
            if (File.Exists(keyPath))
                Info("Using your key " + keyPath + ". If a password is still asked for, the key is not installed yet (option 3 / setup-key).");
            else
                Info("When asked, type the robot's '" + user + "' password. Nothing shows while you type; that is normal.");
            Cmd("ssh " + ForDisplay(args));
            int rc = RunInteractive(sshExe, args);
            if (rc == 255) HandleSshFailure(host);
            else Info("Disconnected from the robot.");
            return rc;
        }

        static void PrintSshFailureHints()
        {
            Fail("ssh could not connect or log in (exit code 255). Read the ssh message above:");
            Info("  'Permission denied': wrong password, or your key is not installed (menu option 3, or setup-key).");
            Info("  'Host key verification failed' or 'REMOTE HOST IDENTIFICATION HAS CHANGED': the device at that");
            Info("  address is not the lab robot, or the robot was reinstalled. Ask the lab maintainer (menu option 9 explains).");
            Info("  'Connection timed out' or 'Could not resolve hostname': the robot or this computer changed");
            Info("  network. Search again (menu option 2, or the find command).");
        }

        // ------------------------------------------------------------------ 3) key login

        static int DoSetupKey(string hostArg, bool interactive)
        {
            string pubPath = keyPath + ".pub";
            string comment = KeyComment();
            Head("Set up key login (one time per computer)");
            if (!File.Exists(keyPath))
            {
                if (sshKeygenExe == null)
                {
                    Fail("ssh-keygen.exe was not found next to ssh.exe. Reinstall the OpenSSH Client (see --help).");
                    return ExitUsage;
                }
                Info("Step 1: create your personal key at " + keyPath);
                Info("A passphrase protects the key if this computer is lost or shared, but you then type the passphrase");
                Info("at each login instead of the robot password. Without one, anyone who copies the key file can log in.");
                bool usePassphrase = AskYesNo("Protect the key with a passphrase? (y/N): ");
                string dir = Path.GetDirectoryName(keyPath);
                if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                string kgArgs = "-t ed25519 -f " + Q(keyPath) + " -C " + Q(comment);
                if (!usePassphrase) kgArgs += " -N " + Q("");
                else Info("ssh-keygen now asks for the passphrase twice (nothing shows while you type).");
                Cmd("ssh-keygen " + kgArgs);
                int krc = RunInteractive(sshKeygenExe, kgArgs);
                if (krc != 0 || !File.Exists(keyPath) || !File.Exists(pubPath))
                {
                    Fail("Creating the key failed (ssh-keygen exit code " + krc + ").");
                    return ExitUsage;
                }
                Good("Key created: " + keyPath + " (private, stays on this computer) and " + pubPath + ".");
            }
            else
            {
                Info("Step 1: you already have a key: " + keyPath);
            }
            if (!File.Exists(pubPath))
            {
                Fail("The public key " + pubPath + " is missing. Delete " + keyPath + " and run this again.");
                return ExitUsage;
            }
            string keyType, keyBase64;
            if (!ReadPublicKey(pubPath, out keyType, out keyBase64))
            {
                Fail("The public key " + pubPath + " is not an ed25519 key (it should start with ssh-ed25519).");
                return ExitUsage;
            }

            Info("Step 2: install the public key on the robot.");
            string host = ResolveHost(hostArg, interactive);
            if (host == null)
            {
                Warn("The key is ready on this computer. Install it later with setup-key (menu option 3) when the robot answers.");
                return ExitNotFound;
            }
            string target = user + "@" + host;
            bool hasPassphrase = KeyHasPassphrase(keyPath);
            if (!hasPassphrase && KeyLoginWorks(target))
            {
                Good("Key login already works for " + target + ". Nothing to install.");
                PrintKeyExplanation(comment, keyBase64);
                return ExitOk;
            }
            string remote =
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && " +
                "(grep -qF '" + keyBase64 + "' ~/.ssh/authorized_keys || echo '" + keyType + " " + keyBase64 + " " + comment +
                "' >> ~/.ssh/authorized_keys) && echo KEY-OK";
            string args = "-t -o ConnectTimeout=8 " + HostKeyOptions() + " " + Q(target) + " " + Q(remote);
            Info("Type the robot's '" + user + "' password when ssh asks (nothing shows while you type). This is the last time you need it here.");
            Cmd("ssh -t ... " + target + " \"<add your public key to ~/.ssh/authorized_keys>\"");
            int rc = RunInteractive(sshExe, args);
            if (rc != 0)
            {
                Fail("Installing the key failed (ssh exit code " + rc + ").");
                if (rc == 255) HandleSshFailure(host);
                return rc;
            }

            Info("Step 3: check that the key works.");
            int vrc;
            if (hasPassphrase)
            {
                Info("Type your key passphrase when asked (not the robot password).");
                string vArgs = "-o ConnectTimeout=8 " + HostKeyOptions() + " -o PreferredAuthentications=publickey " +
                               "-o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -i " + Q(keyPath) + " " + Q(target) + " true";
                vrc = RunInteractive(sshExe, vArgs);
            }
            else
            {
                vrc = KeyLoginWorks(target) ? 0 : 255;
            }
            if (vrc != 0)
            {
                Fail("The key was copied but logging in with it failed (exit code " + vrc + ").");
                Info("Ask the lab maintainer to check ~/.ssh on the robot (it must not be writable by others).");
                return vrc;
            }
            Good("Key login works. Connect (option 1) no longer asks for the robot password.");
            PrintKeyExplanation(comment, keyBase64);
            return ExitOk;
        }

        static void PrintKeyExplanation(string comment, string keyBase64)
        {
            Info("Each lab member adds their own key this way; never share or copy key files.");
            Info("The private key " + keyPath + " stays on this computer only. Never commit it to a repository.");
            Info("To remove this computer's access later: log in to the robot, open ~/.ssh/authorized_keys");
            Info("(for example  nano ~/.ssh/authorized_keys ) and delete the one line that contains");
            Info("  " + keyBase64.Substring(keyBase64.Length - 16) + "   (when this program added it, the line ends with " + comment + "),");
            Info("then delete " + keyPath + " and " + keyPath + ".pub on this computer.");
        }

        static bool KeyLoginWorks(string target)
        {
            string args = "-o BatchMode=yes -o ConnectTimeout=8 " + HostKeyOptions() + " -i " + Q(keyPath) + " " + Q(target) + " true";
            return RunQuiet(sshExe, args, 20000) == 0;
        }

        static bool ReadPublicKey(string path, out string type, out string base64)
        {
            type = null;
            base64 = null;
            try
            {
                string text = File.ReadAllText(path).Trim();
                int nl = text.IndexOfAny(new char[] { '\r', '\n' });
                if (nl >= 0) text = text.Substring(0, nl);
                string[] parts = text.Split(new char[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length < 2) return false;
                if (!parts[0].StartsWith("ssh-ed25519") || !Regex.IsMatch(parts[0], "^[A-Za-z0-9@.-]+$")) return false;
                if (!Base64Regex.IsMatch(parts[1])) return false;
                type = parts[0];
                base64 = parts[1];
                return true;
            }
            catch
            {
                return false;
            }
        }

        // OpenSSH private keys name their cipher in the header: "none" means no passphrase.
        static bool KeyHasPassphrase(string path)
        {
            try
            {
                string text = File.ReadAllText(path);
                if (text.Contains("ENCRYPTED")) return true;
                const string begin = "-----BEGIN OPENSSH PRIVATE KEY-----";
                const string end = "-----END OPENSSH PRIVATE KEY-----";
                int b = text.IndexOf(begin);
                int e = text.IndexOf(end);
                if (b < 0 || e < b) return false;
                string body = Regex.Replace(text.Substring(b + begin.Length, e - b - begin.Length), "\\s", "");
                byte[] data = Convert.FromBase64String(body);
                int off = 15; // "openssh-key-v1\0"
                int len = (data[off] << 24) | (data[off + 1] << 16) | (data[off + 2] << 8) | data[off + 3];
                string cipher = Encoding.ASCII.GetString(data, off + 4, len);
                return cipher != "none";
            }
            catch
            {
                return false;
            }
        }

        static string KeyComment()
        {
            return "turtlebot4-" + Sanitize(Environment.UserName, "user") + "@" + Sanitize(Environment.MachineName, "pc");
        }

        static string Sanitize(string s, string fallback)
        {
            if (string.IsNullOrEmpty(s)) return fallback;
            string r = Regex.Replace(s, "[^A-Za-z0-9._-]", "_");
            return r.Length == 0 ? fallback : r;
        }

        // ------------------------------------------------------------------ 4) status

        static int DoStatus(string hostArg, bool interactive)
        {
            string host = ResolveHost(hostArg, interactive);
            if (host == null) return ExitNotFound;
            string target = user + "@" + host;
            Info("Asking the robot for its status (read only). The battery and dock part asks ROS and can take up to a minute.");
            Cmd("ssh " + ForDisplay(SshOptions() + KeyOption()) + " " + target + " \"<read-only status commands>\"");
            int rc = RunInteractive(sshExe, SshOptions() + KeyOption() + " " + Q(target) + " " + Q(StatusScript));
            if (rc == 255) HandleSshFailure(host);
            return rc;
        }

        // ------------------------------------------------------------------ 5) VS Code

        static int DoVsCode()
        {
            string code = FindVsCode();
            if (code == null)
            {
                Warn("VS Code was not found (no 'code' command on PATH).");
                Info("Install VS Code from https://code.visualstudio.com/ (keep 'Add to PATH' ticked), then add");
                Info("Microsoft's 'Remote - SSH' extension. Steps: " + Guide + ", section Write and run code, Option A.");
                return ExitUsage;
            }
            string host = ResolveHost(null, true);
            if (host == null) return ExitNotFound;
            string remote = user + "@" + host;
            string aliasHost = AliasHostName(ReadLines(sshConfigPath));
            bool useAlias = false;
            if (aliasHost != null)
            {
                // The shortcut works if its HostName is where the robot answered, or answers itself
                // (for example turtlebot4.local while the robot was found by its 10.87 address).
                string aliasTarget = aliasHost.Length == 0 ? AliasName : aliasHost;
                useAlias = string.Equals(aliasTarget, host, StringComparison.OrdinalIgnoreCase) || QuickProbe(aliasTarget);
                if (!useAlias)
                    Warn("Your '" + AliasName + "' shortcut points to " + aliasTarget + ", which did not answer (the robot answered at " +
                         host + "). Edit HostName in " + sshConfigPath + " to use the shortcut.");
            }
            if (useAlias)
            {
                remote = AliasName;
                Info("Using your '" + AliasName + "' shortcut from " + sshConfigPath + " (it uses your key).");
            }
            else
            {
                Info("Without the SSH config shortcut (option 6, plus key login from option 3), VS Code asks for the");
                Info("robot password, sometimes more than once.");
            }
            Info("VS Code needs Microsoft's 'Remote - SSH' extension. If it asks for the platform, choose Linux.");
            Info("The first connection installs the VS Code server on the robot (about 200 MB; up to 10 minutes on campus Wi-Fi).");
            Info("Recommended settings: " + Guide + ", Option A.");
            string folder = "/home/" + user + "/robot_code";
            string cmdArgs = "/d /s /c \"\"" + code + "\" --remote ssh-remote+" + remote + " " + folder + "\"";
            Cmd("code --remote ssh-remote+" + remote + " " + folder);
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo(CmdExe(), cmdArgs);
                psi.UseShellExecute = false;
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit(20000);
                }
                Good("VS Code is opening. Its window shows the connection progress.");
                return ExitOk;
            }
            catch (Exception ex)
            {
                Fail("Could not start VS Code: " + ex.Message);
                return ExitUsage;
            }
        }

        static string FindVsCode()
        {
            string p = FindOnPath("code.cmd");
            if (p != null) return p;
            string[] guesses = {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Programs\Microsoft VS Code\bin\code.cmd"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft VS Code\bin\code.cmd")
            };
            foreach (string g in guesses) if (File.Exists(g)) return g;
            return null;
        }

        // ------------------------------------------------------------------ 6) SSH config shortcut

        static int DoSshConfig()
        {
            string path = sshConfigPath;
            List<string> lines = ReadLines(path);
            if (HasAlias(lines))
            {
                Good("Your SSH config already has a 'Host " + AliasName + "' entry. Nothing was changed.");
                PrintAliasBlock(lines);
                Info("To change it, edit " + path + " yourself.");
                return ExitOk;
            }
            string host = currentHost;
            if (host == null)
            {
                if (!SearchRobot())
                {
                    host = MdnsName;
                    Warn("The robot did not answer, so the shortcut uses the name " + MdnsName + " (works on 'Students' and on");
                    Warn("the robot's own Wi-Fi). Change HostName in the file later if the name does not work.");
                }
                else
                {
                    host = currentHost;
                }
            }

            string text = File.Exists(path) ? File.ReadAllText(path) : "";
            string nl = text.Contains("\r\n") ? "\r\n" : "\n";
            StringBuilder block = new StringBuilder();
            block.Append("Host " + AliasName + nl);
            block.Append("    HostName " + host + nl);
            block.Append("    User " + user + nl);
            bool haveKey = File.Exists(keyPath);
            if (haveKey) block.Append("    IdentityFile " + IdentityFileValue() + nl);
            if (trustNewHostKey)
            {
                // Pinning is switched off for this run (robot reinstalled, tool not updated yet): no pinned lines.
                block.Append("    StrictHostKeyChecking ask" + nl);
            }
            else
            {
                // Same protection as the program's own ssh calls: only the pinned robot key is accepted.
                EnsurePinnedKnownHosts();
                block.Append("    HostKeyAlias " + PinAlias + nl);
                block.Append("    UserKnownHostsFile ~/.ssh/known_hosts " + SshPathValue(PinnedKnownHostsPath()) + nl);
                block.Append("    StrictHostKeyChecking yes" + nl);
                block.Append("    HostKeyAlgorithms ssh-ed25519" + nl);
            }
            block.Append("    ConnectTimeout 8" + nl);

            string prefix = "";
            if (text.Length > 0)
            {
                if (!text.EndsWith("\n")) prefix = nl;
                prefix += nl;
            }
            string dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            if (File.Exists(path))
            {
                string backup = path + ".bak-" + DateTime.Now.ToString("yyyyMMdd-HHmmss");
                File.Copy(path, backup, false);
                Info("Backup of your current file: " + backup);
            }
            File.AppendAllText(path, prefix + block.ToString(), new UTF8Encoding(false));
            Good("Added this block to the end of " + path + " (existing lines were not changed):");
            foreach (string l in block.ToString().Split(new string[] { nl }, StringSplitOptions.RemoveEmptyEntries)) Cmd(l);
            Info("Now you can type  ssh " + AliasName + "  and  scp myfile.py " + AliasName + ":robot_code/ , and VS Code lists");
            Info("'" + AliasName + "' under Remote Explorer.");
            if (!haveKey) Warn("No key yet: after option 3, add the line  IdentityFile ~/.ssh/turtlebot4_ed25519  to the block.");
            if (host.StartsWith("10.87."))
                Warn("10.87.x.x addresses come from the university Wi-Fi and can change. If 'ssh " + AliasName + "' stops working, set HostName to " + MdnsName + " or the new address.");
            return ExitOk;
        }

        static string IdentityFileValue()
        {
            if (string.Equals(keyPath, DefaultKeyPath(), StringComparison.OrdinalIgnoreCase)) return "~/.ssh/turtlebot4_ed25519";
            string p = keyPath.Replace('\\', '/');
            return p.Contains(" ") ? "\"" + p + "\"" : p;
        }

        static List<string> ReadLines(string path)
        {
            List<string> lines = new List<string>();
            try
            {
                if (File.Exists(path)) lines.AddRange(File.ReadAllLines(path));
            }
            catch
            {
                // Unreadable config: treat as empty for the checks.
            }
            return lines;
        }

        static string[] ConfigTokens(string line)
        {
            return line.Trim().Split(new char[] { ' ', '\t', '=' }, StringSplitOptions.RemoveEmptyEntries);
        }

        static bool IsAliasHostLine(string[] tok)
        {
            if (tok.Length < 2 || !string.Equals(tok[0], "Host", StringComparison.OrdinalIgnoreCase)) return false;
            for (int i = 1; i < tok.Length; i++)
                if (string.Equals(tok[i], AliasName, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        static bool HasAlias(List<string> lines)
        {
            foreach (string l in lines) if (IsAliasHostLine(ConfigTokens(l))) return true;
            return false;
        }

        // HostName of the 'Host turtlebot4' block: null if there is no such block, "" if it has no HostName.
        static string AliasHostName(List<string> lines)
        {
            bool inBlock = false;
            bool found = false;
            foreach (string l in lines)
            {
                string[] tok = ConfigTokens(l);
                if (tok.Length == 0) continue;
                string k = tok[0].ToLowerInvariant();
                if (k == "host" || k == "match")
                {
                    inBlock = IsAliasHostLine(tok);
                    if (inBlock) found = true;
                    continue;
                }
                if (inBlock && k == "hostname" && tok.Length >= 2) return tok[1];
            }
            return found ? "" : null;
        }

        static void PrintAliasBlock(List<string> lines)
        {
            bool inBlock = false;
            foreach (string l in lines)
            {
                string[] tok = ConfigTokens(l);
                if (tok.Length > 0)
                {
                    string k = tok[0].ToLowerInvariant();
                    if (k == "host" || k == "match") inBlock = IsAliasHostLine(tok);
                }
                if (inBlock && l.Trim().Length > 0) Cmd(l);
            }
        }

        // ------------------------------------------------------------------ 7) emergency stop

        static int DoStop(string hostArg, bool interactive)
        {
            Say("EMERGENCY STOP: telling the robot's motion programs to stop.", ConsoleColor.Red);
            Say("If the robot is moving towards danger, pick it up now: the wheels stop when it is lifted.", ConsoleColor.Red);
            string host = ResolveHost(hostArg, interactive);
            if (host == null)
            {
                Fail("Could not reach the robot. Pick it up (the Create 3 stops its wheels when lifted) or press the power button on the base.");
                return ExitNotFound;
            }
            string target = user + "@" + host;
            if (!File.Exists(keyPath)) Info("If asked, type the robot's '" + user + "' password.");
            Cmd("ssh " + target + " \"" + StopCommand + "\"");
            int rc = RunInteractive(sshExe, SshOptions() + KeyOption() + " " + Q(target) + " " + Q(StopCommand));
            if (rc == 0)
            {
                Good("STOP sent. A running motion program stops the wheels within a second.");
                Info("The file ~/STOP now blocks new runs of the motion programs. When it is safe to drive again,");
                Info("log in and type:  rm ~/STOP");
                Info("Picking the robot up always stops the wheels (wheel-drop safety on the Create 3).");
            }
            else
            {
                Fail("Sending STOP failed (ssh exit code " + rc + "). Pick the robot up: the wheels stop when it is lifted.");
                if (rc == 255) HandleSshFailure(host);
            }
            return rc;
        }

        // ------------------------------------------------------------------ 8) copy a file

        static int DoCopy()
        {
            if (scpExe == null)
            {
                Fail("scp.exe was not found next to ssh.exe. Reinstall the OpenSSH Client.");
                return ExitUsage;
            }
            Info("Copy a file (or a folder) from this computer into ~/robot_code on the robot.");
            string s = Prompt("Drag the file onto this window, or type its path, then press Enter: ");
            if (string.IsNullOrEmpty(s)) return ExitOk;
            string local = Environment.ExpandEnvironmentVariables(StripQuotes(s));
            bool isDir = Directory.Exists(local);
            if (!isDir && !File.Exists(local))
            {
                Fail("Not found: " + local);
                return ExitUsage;
            }
            local = Path.GetFullPath(local);
            if (isDir && local.Length > 3) local = local.TrimEnd('\\', '/');
            string host = ResolveHost(null, true);
            if (host == null) return ExitNotFound;
            string remote = user + "@" + (host.Contains(":") ? "[" + host + "]" : host) + ":robot_code/";
            string args = "-o ConnectTimeout=8 " + HostKeyOptions() + (isDir ? " -r" : "") + KeyOption() + " " + Q(local) + " " + Q(remote);
            Cmd("scp " + ForDisplay(args));
            int rc = RunInteractive(scpExe, args);
            if (rc == 0) Good("Copied. On the robot it is in ~/robot_code/" + Path.GetFileName(local));
            else
            {
                Fail("Copy failed (scp exit code " + rc + "). Check that ~/robot_code exists on the robot.");
                if (!trustNewHostKey && HostKeyMismatch(user + "@" + host)) PrintHostKeyMismatch(host);
            }
            return rc;
        }

        // ------------------------------------------------------------------ 9) host key changed

        static int DoFixHostKey()
        {
            if (sshKeygenExe == null)
            {
                Fail("ssh-keygen.exe was not found next to ssh.exe. Reinstall the OpenSSH Client.");
                return ExitUsage;
            }
            Head("Fix 'WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!'");
            Info("This program checks the robot's identity against the host key built into it:");
            Info("  " + PinnedFingerprint());
            Info("A device with another key is refused before any password prompt. If that happens, either the address");
            Info("is not the lab robot, or the robot was reinstalled and this program must be updated by the lab");
            Info("maintainer (README.md in this program's folder, section Host key pinning). Nothing on this computer");
            Info("needs fixing for that, and this option does not change it.");
            Console.WriteLine();
            Info("Plain ssh (and VS Code without option 6) instead remembers each robot's identity in");
            Info("~/.ssh/known_hosts and warns when it changes. This option removes the old entry there. That is expected");
            Info("when the robot's SD card was reinstalled, or when the address now belongs to another device. It can also");
            Info("mean another device is pretending to be the robot.");
            Warn("Continue only after the lab maintainer confirms the robot was reinstalled or its address changed.");
            string def = currentHost != null ? currentHost : MdnsName;
            string s = Prompt("Name or address shown in the warning [" + def + "]: ");
            if (s == null) return ExitOk;
            string host = s.Length == 0 ? def : NormalizeHost(s);
            if (host == null)
            {
                Warn("That does not look like a name or address. Nothing was changed.");
                return ExitUsage;
            }
            string answer = Prompt("Type yes to forget the saved identity of " + host + ": ");
            if (answer == null || answer.ToLowerInvariant() != "yes")
            {
                Info("Cancelled. Nothing was changed.");
                return ExitOk;
            }
            string args = "-R " + Q(host) + (knownHostsPath != null ? " -f " + Q(knownHostsPath) : "");
            Cmd("ssh-keygen " + args);
            int rc = RunInteractive(sshKeygenExe, args);
            if (rc == 0) Good("Done. The next plain ssh connection asks you to confirm the robot's new identity: compare its fingerprint with the lab maintainer's.");
            else Fail("ssh-keygen failed (exit code " + rc + ").");
            return rc;
        }

        // ------------------------------------------------------------------ host key pinning

        static string SshOptions()
        {
            return "-o ConnectTimeout=8 -o ServerAliveInterval=15 " + HostKeyOptions();
        }

        // Options that make ssh and scp accept only the pinned robot key (or, with --trust-new-host-key, ask).
        static string HostKeyOptions()
        {
            if (trustNewHostKey)
            {
                string o = "-o StrictHostKeyChecking=ask";
                if (knownHostsPath != null) o += " -o " + Q("UserKnownHostsFile=" + SshPathValue(knownHostsPath));
                return o;
            }
            EnsurePinnedKnownHosts();
            return "-o HostKeyAlias=" + PinAlias + " -o " + Q("UserKnownHostsFile=" + SshPathValue(PinnedKnownHostsPath())) +
                   " -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 -o CheckHostIP=no";
        }

        // Shortens the displayed command: the host key options are long and the same every time.
        static string ForDisplay(string args)
        {
            if (trustNewHostKey) return args;
            return args.Replace(HostKeyOptions(), "[robot host key check]");
        }

        // Writes the program's own known_hosts file (one line: the pinned key under PinAlias) if it differs.
        static void EnsurePinnedKnownHosts()
        {
            string path = PinnedKnownHostsPath();
            string content = PinAlias + " " + pinnedHostKey + "\n";
            try
            {
                if (File.Exists(path) && File.ReadAllText(path) == content) return;
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllText(path, content, new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                throw new IOException("could not write " + path + " (" + ex.Message + ")");
            }
        }

        // A path as ssh expects it in an option or config file: ~/... when under the user profile,
        // forward slashes, and double quotes when it contains a space.
        static string SshPathValue(string path)
        {
            string p = path;
            string home = UserProfile();
            if (!string.IsNullOrEmpty(home) && p.StartsWith(home.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                p = "~" + p.Substring(home.TrimEnd('\\').Length);
            p = p.Replace('\\', '/');
            return p.Contains(" ") ? "\"" + p + "\"" : p;
        }

        static string PinnedFingerprint()
        {
            try
            {
                byte[] blob = Convert.FromBase64String(pinnedHostKey.Split(' ')[1]);
                using (System.Security.Cryptography.SHA256 sha = System.Security.Cryptography.SHA256.Create())
                {
                    return "SHA256:" + Convert.ToBase64String(sha.ComputeHash(blob)).TrimEnd('=');
                }
            }
            catch
            {
                return "(unknown)";
            }
        }

        // After ssh failed: asks ssh again, without any password prompt, whether the host key was the problem.
        static bool HostKeyMismatch(string target)
        {
            if (trustNewHostKey) return false;
            string output;
            string args = "-o BatchMode=yes -o ConnectTimeout=5 " + HostKeyOptions() + KeyOption() + " " + Q(target) + " true";
            RunCaptured(sshExe, args, 20000, out output);
            return output.Contains("REMOTE HOST IDENTIFICATION HAS CHANGED") || output.Contains("Host key verification failed") ||
                   output.Contains("no matching host key type") || output.Contains("host key is known");
        }

        static void HandleSshFailure(string host)
        {
            if (HostKeyMismatch(user + "@" + host)) PrintHostKeyMismatch(host);
            else PrintSshFailureHints();
        }

        static void PrintHostKeyMismatch(string host)
        {
            Fail("The device at " + host + " is not the lab robot as this program knows it: its SSH host key is not the");
            Fail("built-in robot key. ssh stopped before asking for any password, so nothing was sent.");
            Info("Either this address is not the lab robot (another device on the network), or the robot was reinstalled.");
            Info("Ask the lab maintainer. If the robot was reinstalled, the pinned key in this program must be updated");
            Info("(README.md in this program's folder, section Host key pinning).");
            Info("Expected fingerprint: " + PinnedFingerprint());
            Info("Do not edit " + PinnedKnownHostsPath() + ": the program rewrites it.");
            Info("Only if the maintainer confirms a reinstall and no updated program exists yet: run the program with");
            Info("--trust-new-host-key, and continue only if the fingerprint ssh shows is the one the maintainer reads on the robot.");
        }

        static void PrintTrustNewWarning()
        {
            Warn("--trust-new-host-key: the robot's identity is NOT checked against the built-in host key.");
            Warn("If ssh asks whether to trust the robot, continue only if the fingerprint it shows is the one the lab");
            Warn("maintainer read on the robot (ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub). The key built into");
            Warn("this program has fingerprint " + PinnedFingerprint() + "; you can paste the expected fingerprint at ssh's prompt.");
        }

        // ------------------------------------------------------------------ ssh and process helpers

        static string DefaultKeyPath()
        {
            return Path.Combine(Path.Combine(UserProfile(), ".ssh"), "turtlebot4_ed25519");
        }

        static string UserProfile()
        {
            string p = Environment.GetEnvironmentVariable("USERPROFILE");
            if (string.IsNullOrEmpty(p)) p = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            return p;
        }

        static string KeyOption()
        {
            return File.Exists(keyPath) ? " -i " + Q(keyPath) : "";
        }

        static bool RequireSsh()
        {
            if (LocateSsh()) return true;
            PrintSshMissing();
            return false;
        }

        static bool LocateSsh()
        {
            if (sshExe != null) return true;
            sshExe = FindTool("ssh.exe");
            if (sshExe == null) return false;
            string dir = Path.GetDirectoryName(sshExe);
            sshKeygenExe = File.Exists(Path.Combine(dir, "ssh-keygen.exe")) ? Path.Combine(dir, "ssh-keygen.exe") : FindTool("ssh-keygen.exe");
            scpExe = File.Exists(Path.Combine(dir, "scp.exe")) ? Path.Combine(dir, "scp.exe") : FindTool("scp.exe");
            return true;
        }

        static string FindTool(string name)
        {
            string win = Environment.GetEnvironmentVariable("WINDIR");
            if (string.IsNullOrEmpty(win)) win = Environment.GetEnvironmentVariable("SystemRoot");
            if (!string.IsNullOrEmpty(win))
            {
                foreach (string sub in new string[] { @"System32\OpenSSH", @"Sysnative\OpenSSH" })
                {
                    string p = Path.Combine(Path.Combine(win, sub), name);
                    if (File.Exists(p)) return p;
                }
            }
            return FindOnPath(name);
        }

        static string FindOnPath(string name)
        {
            string path = Environment.GetEnvironmentVariable("PATH");
            if (string.IsNullOrEmpty(path)) return null;
            foreach (string raw in path.Split(';'))
            {
                string d = raw.Trim().Trim('"');
                if (d.Length == 0) continue;
                try
                {
                    string p = Path.Combine(d, name);
                    if (File.Exists(p)) return p;
                }
                catch
                {
                    // Malformed PATH entry.
                }
            }
            return null;
        }

        static string CmdExe()
        {
            string c = Environment.GetEnvironmentVariable("ComSpec");
            if (!string.IsNullOrEmpty(c) && File.Exists(c)) return c;
            return Path.Combine(Environment.SystemDirectory, "cmd.exe");
        }

        static void PrintSshMissing()
        {
            Fail("ssh (the OpenSSH Client) was not found on this computer.");
            Info("Windows 10 and 11 include it, but it can be switched off. To add it:");
            Info("  1. Open Settings > System > Optional features (Windows 10: Settings > Apps > Optional features).");
            Info("  2. Choose 'View features' (or 'Add a feature'), search for 'OpenSSH Client' and install it.");
            Info("Or, in PowerShell opened with 'Run as administrator', run:");
            Cmd("Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0");
            Info("Then start this program again.");
        }

        // Runs a program in this console window (keyboard and screen shared), waits, returns its exit code.
        static int RunInteractive(string exe, string args)
        {
            ResetColor();
            IntPtr hIn = GetStdHandle(-10);
            IntPtr hOut = GetStdHandle(-11);
            uint inMode, outMode;
            bool haveIn = GetConsoleMode(hIn, out inMode);
            bool haveOut = GetConsoleMode(hOut, out outMode);
            ProcessStartInfo psi = new ProcessStartInfo(exe, args);
            psi.UseShellExecute = false;
            childRunning = true;
            try
            {
                using (Process p = Process.Start(psi))
                {
                    p.WaitForExit();
                    return p.ExitCode;
                }
            }
            catch (System.ComponentModel.Win32Exception ex)
            {
                Fail("Could not start " + exe + ": " + ex.Message);
                return ExitUsage;
            }
            finally
            {
                childRunning = false;
                // ssh switches the console to raw mode; put it back even if ssh did not.
                if (haveIn) SetConsoleMode(hIn, inMode);
                if (haveOut) SetConsoleMode(hOut, outMode);
            }
        }

        // Runs a program with no input and hidden output; returns its exit code, or -1 on timeout.
        static int RunQuiet(string exe, string args, int timeoutMs)
        {
            ProcessStartInfo psi = new ProcessStartInfo(exe, args);
            psi.UseShellExecute = false;
            psi.RedirectStandardInput = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            using (Process p = Process.Start(psi))
            {
                p.OutputDataReceived += delegate { };
                p.ErrorDataReceived += delegate { };
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();
                p.StandardInput.Close();
                if (!p.WaitForExit(timeoutMs))
                {
                    try { p.Kill(); } catch { }
                    return -1;
                }
                p.WaitForExit();
                return p.ExitCode;
            }
        }

        // Runs a program with no input; collects its output and error text. Returns the exit code, or -1 on timeout.
        static int RunCaptured(string exe, string args, int timeoutMs, out string output)
        {
            StringBuilder sb = new StringBuilder();
            ProcessStartInfo psi = new ProcessStartInfo(exe, args);
            psi.UseShellExecute = false;
            psi.RedirectStandardInput = true;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            DataReceivedEventHandler collect = delegate(object sender, DataReceivedEventArgs e)
            {
                if (e.Data != null) lock (sb) { sb.AppendLine(e.Data); }
            };
            int rc;
            using (Process p = Process.Start(psi))
            {
                p.OutputDataReceived += collect;
                p.ErrorDataReceived += collect;
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();
                p.StandardInput.Close();
                if (!p.WaitForExit(timeoutMs))
                {
                    try { p.Kill(); } catch { }
                    rc = -1;
                }
                else
                {
                    p.WaitForExit();
                    rc = p.ExitCode;
                }
            }
            lock (sb) { output = sb.ToString(); }
            return rc;
        }

        // Quotes one argument for the Windows command line (the rules ssh.exe's C runtime uses to split it).
        static string Q(string arg)
        {
            if (arg.Length > 0 && arg.IndexOfAny(new char[] { ' ', '\t', '\n', '"' }) < 0) return arg;
            StringBuilder sb = new StringBuilder("\"");
            int backslashes = 0;
            foreach (char c in arg)
            {
                if (c == '\\')
                {
                    backslashes++;
                    continue;
                }
                if (c == '"')
                {
                    sb.Append('\\', backslashes * 2 + 1);
                    sb.Append('"');
                }
                else
                {
                    sb.Append('\\', backslashes);
                    sb.Append(c);
                }
                backslashes = 0;
            }
            sb.Append('\\', backslashes * 2);
            sb.Append('"');
            return sb.ToString();
        }

        static string StripQuotes(string s)
        {
            s = s.Trim();
            if (s.Length >= 2 && ((s[0] == '"' && s[s.Length - 1] == '"') || (s[0] == '\'' && s[s.Length - 1] == '\'')))
                s = s.Substring(1, s.Length - 2).Trim();
            return s;
        }

        // Accepts "10.87.10.205", "turtlebot4.local", "ubuntu@10.42.0.1", "ssh ubuntu@x", "[fe80::1]".
        static string NormalizeHost(string s)
        {
            if (s == null) return null;
            s = StripQuotes(s);
            if (s.StartsWith("ssh ", StringComparison.OrdinalIgnoreCase)) s = s.Substring(4).Trim();
            int at = s.LastIndexOf('@');
            if (at >= 0) s = s.Substring(at + 1);
            s = s.Trim().TrimEnd('/');
            if (s.StartsWith("[") && s.EndsWith("]")) s = s.Substring(1, s.Length - 2);
            return HostRegex.IsMatch(s) ? s : null;
        }

        // ------------------------------------------------------------------ console helpers

        static void Say(string text, ConsoleColor color)
        {
            try { Console.ForegroundColor = color; } catch { }
            Console.WriteLine(text);
            ResetColor();
        }

        static void ResetColor()
        {
            try { Console.ResetColor(); } catch { }
        }

        static void Info(string text) { Say(text, ConsoleColor.Gray); }
        static void Good(string text) { Say(text, ConsoleColor.Green); }
        static void Warn(string text) { Say(text, ConsoleColor.Yellow); }
        static void Fail(string text) { Say(text, ConsoleColor.Red); }
        static void Head(string text) { Say(text, ConsoleColor.Cyan); }
        static void Cmd(string text) { Say("    " + text, ConsoleColor.DarkGray); }

        // Returns the trimmed line, or null at end of input.
        static string Prompt(string text)
        {
            try { Console.ForegroundColor = ConsoleColor.White; } catch { }
            Console.Write(text);
            ResetColor();
            string s = Console.ReadLine();
            if (s == null)
            {
                Console.WriteLine();
                return null;
            }
            if (Console.IsInputRedirected) Console.WriteLine(s); // echo piped input so logs read naturally
            return s.Trim();
        }

        static bool AskYesNo(string text)
        {
            string s = Prompt(text);
            if (s == null) return false;
            s = s.ToLowerInvariant();
            return s == "y" || s == "yes";
        }

        // Pauses only when this program has its own console window (started by double-click),
        // so the window does not vanish before the message can be read.
        static void PauseIfOwnConsole()
        {
            try
            {
                if (Console.IsInputRedirected) return;
                uint[] list = new uint[8];
                if (GetConsoleProcessList(list, (uint)list.Length) != 1) return;
                Prompt("Press Enter to close...");
            }
            catch
            {
                // Never fail because of the pause.
            }
        }
    }
}
