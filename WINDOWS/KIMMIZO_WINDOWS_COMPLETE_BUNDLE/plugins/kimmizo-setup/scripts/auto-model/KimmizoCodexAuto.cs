using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace Kimmizo.CodexAuto
{
    internal sealed class RouteData
    {
        public string model { get; set; }
        public string effort { get; set; }
        public string tier { get; set; }
        public bool requiresUltraApproval { get; set; }
        public bool modelObserved { get; set; }
    }

    internal sealed class StateData
    {
        public bool defaultAuto { get; set; }
        public List<string> autoThreads { get; set; }
        public List<string> secretaryThreads { get; set; }
        public List<string> ultraApprovalThreads { get; set; }
        public Dictionary<string, RouteData> lastRoutes { get; set; }
        public VoiceStateData voiceBootstrap { get; set; }

        public StateData()
        {
            defaultAuto = true;
            autoThreads = new List<string>();
            secretaryThreads = new List<string>();
            ultraApprovalThreads = new List<string>();
            lastRoutes = new Dictionary<string, RouteData>(StringComparer.OrdinalIgnoreCase);
            voiceBootstrap = new VoiceStateData();
        }
    }

    internal sealed class DefaultAutoPreferenceData
    {
        public int schemaVersion { get; set; }
        public bool enabled { get; set; }
    }

    internal sealed class PendingRequest
    {
        public string method { get; set; }
        public bool autoStart { get; set; }
        public bool firstModelPage { get; set; }
    }

    internal sealed class TransformResult
    {
        public string ForwardLine { get; set; }
        public string ImmediateResponse { get; set; }
    }

    internal sealed class VoiceBootstrapData
    {
        public int schemaVersion { get; set; }
        public string policyVersion { get; set; }
        public string policySha256 { get; set; }
        public string trigger { get; set; }
        public string pronoun { get; set; }
        public string suffix { get; set; }
        public string instruction { get; set; }
        public string blockedMessage { get; set; }
        public string source { get; set; }
    }

    internal sealed class ProjectCapsuleManifestData
    {
        public string schema { get; set; }
        public int schema_version { get; set; }
        public string project_id { get; set; }
        public string capsule_version { get; set; }
        public string core_version { get; set; }
        public string adapter_version { get; set; }
        public string source_revision { get; set; }
        public string provenance { get; set; }
        public Dictionary<string, string> file_hashes { get; set; }
        public string aggregate_sha256 { get; set; }
        public string bootstrap_sha256 { get; set; }
        public string bootstrap_hash { get; set; }
        public string policy_sha256 { get; set; }
        public string migration_sha256 { get; set; }
        public string agents_block_sha256 { get; set; }
        public string active_revision { get; set; }
        public string previous_revision { get; set; }
        public CapsuleCompatibilityData compatibility { get; set; }
        public string lifecycle { get; set; }
    }

    internal sealed class CapsuleCompatibilityData
    {
        public string minimum_setup_version { get; set; }
    }

    internal sealed class PolicyData
    {
        public int schema_version { get; set; }
        public string policy_version { get; set; }
        public UsagePolicyData usage_policy { get; set; }
        public Dictionary<string, ModelPolicyData> model_selection { get; set; }
        public ThresholdPolicyData thresholds { get; set; }
        public VoicePolicyData voice { get; set; }
    }

    internal sealed class UsagePolicyData
    {
        public string mode { get; set; }
        public string default_model { get; set; }
        public string default_effort { get; set; }
        public List<string> manual_only_models { get; set; }
        public bool automatic_multi_agent { get; set; }
        public bool fast_mode { get; set; }
        public string execution_mode { get; set; }
        public bool verify_before_escalation { get; set; }
        public List<string> escalation_order { get; set; }
    }

    internal sealed class ModelPolicyData
    {
        public string effort { get; set; }
        public string pending_effort { get; set; }
        public List<string> signals { get; set; }
        public List<string> models { get; set; }
        public bool requires_approval { get; set; }
    }

    internal sealed class ThresholdPolicyData
    {
        public int fast_max_chars { get; set; }
        public int deep_min_chars { get; set; }
        public int ultra_min_chars { get; set; }
    }

    internal sealed class VoicePolicyData
    {
        public string trigger { get; set; }
        public string pronoun { get; set; }
        public string suffix { get; set; }
        public string instruction { get; set; }
        public string blocked_message { get; set; }
    }

    internal sealed class VoiceStateData
    {
        public string status { get; set; }
        public string source { get; set; }
        public string policyVersion { get; set; }
        public string policySha256 { get; set; }
        public string verifiedAt { get; set; }
        public string reason { get; set; }

        public VoiceStateData()
        {
            status = "unverified";
        }
    }

    internal static class Program
    {
        private const string VirtualModel = "kimmizo-auto";
        private const string VirtualDisplayName = "✦ Auto";
        private const string VirtualDescription = "ปรับโมเดลตามช่วงงาน";
        private const int PolicySchemaVersion = 3;
        private const string PolicyVersion = "3.0.0";
        private const string PolicyTrigger = "เลขาคิม";
        private const string FixedVoiceBlockedMessage = "ยังตรวจสอบ voice bootstrap ของเลขาคิมไม่สำเร็จ จึงไม่เริ่มงานสาระสำคัญค่ะ";
        private const string FixedModelUnverifiedMessage = "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานสาระสำคัญค่ะ";
        private const string FixedContextUnverifiedMessage = "additionalContext ของงาน Ultra ไม่อยู่ในรูปแบบที่ปลอดภัย จึงไม่เริ่มงานสาระสำคัญค่ะ";
        private const int VoiceBlockedCode = -32071;
        private const int ModelUnverifiedCode = -32072;
        private const int ContextUnverifiedCode = -32073;
        private const string VoiceBootstrapFileName = "voice-bootstrap.json";
        private const string PolicyFileName = "model-policy.json";
        private const string PolicyHashFileName = "model-policy.sha256";
        private const string DefaultAutoPreferenceFileName = "default-auto.json";
        private const int DefaultAutoPreferenceSchemaVersion = 1;
        private const string ProjectCapsuleSchema = "kimmizo-capsule-v2";
        private const int ProjectCapsuleSchemaVersion = 2;
        private const string ProjectCapsuleProvenance = "vendored_project_local_snapshot";
        private const string ProjectCapsuleMinimumSetupVersion = "1.0.0";
        private const string ProjectVoiceBootstrapRelativePath = ".kimmizo/voice-bootstrap.json";
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        private static readonly object StateGate = new object();
        private static readonly object PendingGate = new object();
        private static readonly object CatalogGate = new object();
        private static readonly Dictionary<string, PendingRequest> Pending = new Dictionary<string, PendingRequest>();
        private static readonly HashSet<string> AvailableModels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, HashSet<string>> AvailableEfforts = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
        private static string CatalogDefaultModel = "gpt-5.6-luna";
        private static StateData State = LoadState();

        private static string InstallRoot
        {
            get { return AppDomain.CurrentDomain.BaseDirectory; }
        }

        private static string StatePath
        {
            get { return Path.Combine(InstallRoot, "state.json"); }
        }

        private static string DefaultAutoPreferencePath
        {
            get { return Path.Combine(InstallRoot, DefaultAutoPreferenceFileName); }
        }

        private static string RealCodexPath
        {
            get { return Path.Combine(InstallRoot, "codex-real.exe"); }
        }

        private static string RuntimeSyncScriptPath
        {
            get { return Path.Combine(InstallRoot, "Sync-KimmizoCodexRuntime.ps1"); }
        }

        private static string RuntimeSyncStatePath
        {
            get { return Path.Combine(InstallRoot, "runtime-sync.json"); }
        }

        private static string PolicyPath
        {
            get { return Path.Combine(InstallRoot, PolicyFileName); }
        }

        private static string PolicyHashPath
        {
            get { return Path.Combine(InstallRoot, PolicyHashFileName); }
        }

        public static int Main(string[] args)
        {
            Console.InputEncoding = new UTF8Encoding(false);
            Console.OutputEncoding = new UTF8Encoding(false);

            if (args.Any(delegate(string value) { return value == "--kimmizo-default-auto-on"; }))
            {
                SetDefaultAuto(true);
                Console.WriteLine("{\"defaultAuto\":true}");
                return 0;
            }
            if (args.Any(delegate(string value) { return value == "--kimmizo-default-auto-off"; }))
            {
                SetDefaultAuto(false);
                Console.WriteLine("{\"defaultAuto\":false}");
                return 0;
            }
            if (args.Any(delegate(string value) { return value == "--kimmizo-self-test"; }))
            {
                return RunSelfTest();
            }
            if (args.Any(delegate(string value) { return value == "--kimmizo-status"; }))
            {
                return WriteStatus();
            }
            if (!TrySyncRuntime())
            {
                Console.Error.WriteLine("Kimmizo Auto refused to start an unverified Codex runtime bundle.");
                return 3;
            }
            if (!File.Exists(RealCodexPath))
            {
                Console.Error.WriteLine("Kimmizo Auto cannot find its signed Codex runtime: " + RealCodexPath);
                return 2;
            }

            bool appServer = args.Any(delegate(string value) { return value == "app-server"; });
            if (!appServer)
            {
                return RunPassthrough(args);
            }
            return RunJsonLineProxy(args);
        }

        private static bool TrySyncRuntime()
        {
            if (!File.Exists(RuntimeSyncScriptPath)) return false;
            try
            {
                string systemRoot = Environment.GetEnvironmentVariable("WINDIR") ?? Environment.GetEnvironmentVariable("SystemRoot") ?? @"C:\Windows";
                string powershell = Path.Combine(systemRoot, @"System32\WindowsPowerShell\v1.0\powershell.exe");
                ProcessStartInfo start = new ProcessStartInfo();
                start.FileName = powershell;
                start.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + QuoteArgument(RuntimeSyncScriptPath) + " -InstallRoot " + QuoteArgument(InstallRoot) + " -Quiet";
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.RedirectStandardError = false;
                using (Process sync = Process.Start(start))
                {
                    sync.WaitForExit();
                    if (sync.ExitCode != 0)
                    {
                        Console.Error.WriteLine("Kimmizo Auto runtime sync could not verify a safe runtime bundle.");
                        return false;
                    }
                }
                return true;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("Kimmizo Auto runtime sync failed. " + error.Message);
                return false;
            }
        }

        private static void PrepareRuntimeEnvironment(ProcessStartInfo start)
        {
            string currentPath = start.EnvironmentVariables["PATH"] ?? Environment.GetEnvironmentVariable("PATH") ?? String.Empty;
            start.EnvironmentVariables["PATH"] = InstallRoot + Path.PathSeparator + currentPath;
        }

        private static int RunPassthrough(string[] args)
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = RealCodexPath;
            start.Arguments = JoinArguments(args);
            start.UseShellExecute = false;
            PrepareRuntimeEnvironment(start);
            Process child = Process.Start(start);
            child.WaitForExit();
            return child.ExitCode;
        }

        private static int RunJsonLineProxy(string[] args)
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = RealCodexPath;
            start.Arguments = JoinArguments(args);
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardInput = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            PrepareRuntimeEnvironment(start);

            using (Process child = new Process())
            {
                child.StartInfo = start;
                child.Start();
                StreamWriter childInput = new StreamWriter(child.StandardInput.BaseStream, new UTF8Encoding(false));
                childInput.AutoFlush = true;

                Thread output = new Thread(delegate()
                {
                    try
                    {
                        string line;
                        while ((line = child.StandardOutput.ReadLine()) != null)
                        {
                            Console.Out.WriteLine(TransformServerLine(line));
                            Console.Out.Flush();
                        }
                    }
                    catch (IOException)
                    {
                    }
                });
                output.IsBackground = true;
                output.Start();

                Thread error = new Thread(delegate()
                {
                    try
                    {
                        string line;
                        while ((line = child.StandardError.ReadLine()) != null)
                        {
                            Console.Error.WriteLine(line);
                            Console.Error.Flush();
                        }
                    }
                    catch (IOException)
                    {
                    }
                });
                error.IsBackground = true;
                error.Start();

                try
                {
                    string line;
                    while ((line = Console.In.ReadLine()) != null)
                    {
                        TransformResult transformed = TransformClientLine(line);
                        if (!String.IsNullOrWhiteSpace(transformed.ImmediateResponse))
                        {
                            Console.Out.WriteLine(transformed.ImmediateResponse);
                            Console.Out.Flush();
                        }
                        if (!String.IsNullOrWhiteSpace(transformed.ForwardLine))
                        {
                            childInput.WriteLine(transformed.ForwardLine);
                            childInput.Flush();
                        }
                    }
                }
                catch (IOException)
                {
                }
                finally
                {
                    try { childInput.Close(); } catch (IOException) { }
                }

                child.WaitForExit();
                output.Join(3000);
                error.Join(3000);
                return child.ExitCode;
            }
        }

        private static TransformResult TransformClientLine(string line)
        {
            line = line == null ? null : line.TrimStart('\uFEFF');
            Dictionary<string, object> message = ParseObject(line);
            if (message == null)
            {
                return new TransformResult { ForwardLine = line };
            }

            string method = GetString(message, "method");
            Dictionary<string, object> parameters = GetObject(message, "params");
            bool changed = false;
            PendingRequest pending = null;

            if (method == "model/list")
            {
                pending = new PendingRequest();
                pending.method = method;
                pending.firstModelPage = parameters == null || !parameters.ContainsKey("cursor") || parameters["cursor"] == null;
            }
            else if (method == "config/read")
            {
                pending = new PendingRequest { method = method };
            }
            else if (method == "config/value/write" && parameters != null)
            {
                changed = HandleConfigWrite(parameters) || changed;
                pending = new PendingRequest { method = method };
            }
            else if (method == "config/batchWrite" && parameters != null)
            {
                IList edits = GetArray(parameters, "edits");
                if (edits != null)
                {
                    foreach (object item in edits)
                    {
                        Dictionary<string, object> edit = item as Dictionary<string, object>;
                        if (edit != null)
                        {
                            changed = HandleConfigWrite(edit) || changed;
                        }
                    }
                }
                pending = new PendingRequest { method = method };
            }
            else if (method == "thread/start" && parameters != null)
            {
                string requestedModel = GetString(parameters, "model");
                bool auto = String.IsNullOrWhiteSpace(requestedModel) ? GetDefaultAuto() : IsVirtual(requestedModel);
                pending = new PendingRequest { method = method, autoStart = auto };
                if (auto)
                {
                    RouteData route = ChooseRoute(String.Empty);
                    if (!IsObservedRoute(route))
                    {
                        return BuildBlockedTransform(message, ModelUnverifiedCode, FixedModelUnverifiedMessage);
                    }
                    parameters["model"] = route.model;
                    SetThreadStartEffort(parameters, route.effort);
                    changed = true;
                }
            }
            else if (method == "thread/settings/update" && parameters != null)
            {
                string threadId = GetString(parameters, "threadId");
                if (parameters.ContainsKey("model"))
                {
                    string requested = Convert.ToString(parameters["model"], CultureInfo.InvariantCulture);
                    if (IsVirtual(requested))
                    {
                        RouteData route = GetLastRoute(threadId) ?? ChooseRoute(String.Empty);
                        if (!IsObservedRoute(route))
                        {
                            return BuildBlockedTransform(message, ModelUnverifiedCode, FixedModelUnverifiedMessage);
                        }
                        SetThreadAuto(threadId, true, route);
                        parameters["model"] = route.model;
                        parameters["effort"] = route.effort;
                        RewriteCollaborationMode(parameters, route);
                        changed = true;
                    }
                    else if (!String.IsNullOrWhiteSpace(requested))
                    {
                        SetThreadAuto(threadId, false, null);
                    }
                }
                pending = new PendingRequest { method = method };
            }
            else if (method == "turn/start" && parameters != null)
            {
                string threadId = GetString(parameters, "threadId");
                bool auto = IsVirtual(GetString(parameters, "model")) || IsThreadAuto(threadId);
                if (auto)
                {
                    string taskText = ExtractTaskText(GetArray(parameters, "input"));
                    bool secretary = IsSecretaryThread(threadId) || IsSecretaryTrigger(taskText);
                    bool firstSecretaryTrigger = !IsSecretaryThread(threadId) && IsSecretaryTrigger(taskText);
                    if (secretary)
                    {
                        VoiceBootstrapData voiceBootstrap;
                        string voiceStatus;
                        string voiceReason;
                        if (TryLoadVoiceBootstrap(out voiceBootstrap, out voiceStatus, out voiceReason))
                        {
                            if (InjectVoiceBootstrap(parameters, voiceBootstrap))
                            {
                                SetVoiceStatus("enforced", voiceBootstrap.source, voiceBootstrap.policyVersion, voiceBootstrap.policySha256, null);
                                changed = true;
                            }
                            else
                            {
                                SetVoiceStatus("unverified", voiceBootstrap.source, voiceBootstrap.policyVersion, voiceBootstrap.policySha256, "The turn additionalContext value is not an object.");
                                if (firstSecretaryTrigger || IsSubstantiveWorkflow(taskText))
                                {
                                    return BuildBlockedTransform(message, VoiceBlockedCode, FixedVoiceBlockedMessage);
                                }
                            }
                        }
                        else
                        {
                            SetVoiceStatus("unverified", null, null, null, voiceReason);
                            if (firstSecretaryTrigger || IsSubstantiveWorkflow(taskText))
                            {
                                return BuildBlockedTransform(message, VoiceBlockedCode, FixedVoiceBlockedMessage);
                            }
                        }
                    }
                    bool denialIntent = IsUltraDenial(taskText);
                    bool ultraApproved = IsUltraPending(threadId) && !denialIntent && IsUltraApproval(taskText);
                    RouteData route = denialIntent
                        ? ChooseRoute(String.Empty)
                        : ChooseAdaptiveRoute(GetLastRoute(threadId), taskText, ultraApproved, ultraApproved);
                    if (denialIntent)
                    {
                        SetUltraPending(threadId, false);
                    }
                    if (!IsObservedRoute(route))
                    {
                        return BuildBlockedTransform(message, ModelUnverifiedCode, FixedModelUnverifiedMessage);
                    }
                    if (ultraApproved)
                    {
                        SetUltraPending(threadId, false);
                    }
                    if (route.requiresUltraApproval)
                    {
                        if (!AddUltraApprovalContext(parameters))
                        {
                            return BuildBlockedTransform(message, ContextUnverifiedCode, FixedContextUnverifiedMessage);
                        }
                        SetUltraPending(threadId, true);
                    }
                    if (firstSecretaryTrigger) SetSecretaryThread(threadId, true);
                    SetThreadAuto(threadId, true, route);
                    parameters["model"] = route.model;
                    parameters["effort"] = route.effort;
                    RewriteCollaborationMode(parameters, route);
                    changed = true;
                }
                pending = new PendingRequest { method = method };
            }
            else if (method == "thread/read" || method == "thread/list" || method == "thread/resume")
            {
                pending = new PendingRequest { method = method };
            }
            else if ((method == "thread/delete" || method == "thread/removed" || method == "thread/closed") && parameters != null)
            {
                SetThreadAuto(GetString(parameters, "threadId"), false, null);
                pending = new PendingRequest { method = method };
            }

            if (pending != null && message.ContainsKey("id"))
            {
                lock (PendingGate)
                {
                    Pending[IdKey(message["id"])] = pending;
                }
            }
            return new TransformResult { ForwardLine = changed ? Json.Serialize(message) : line };
        }

        private static string TransformServerLine(string line)
        {
            Dictionary<string, object> message = ParseObject(line);
            if (message == null)
            {
                return line;
            }

            bool changed = false;
            PendingRequest pending = null;
            if (message.ContainsKey("id"))
            {
                string key = IdKey(message["id"]);
                lock (PendingGate)
                {
                    if (Pending.ContainsKey(key))
                    {
                        pending = Pending[key];
                        Pending.Remove(key);
                    }
                }
            }

            Dictionary<string, object> result = GetObject(message, "result");
            if (pending != null && result != null)
            {
                if (pending.method == "model/list" && pending.firstModelPage)
                {
                    changed = AddAutoModel(result) || changed;
                }
                else if (pending.method == "config/read")
                {
                    changed = RewriteConfigRead(result) || changed;
                }
                else if (pending.method == "thread/start")
                {
                    Dictionary<string, object> thread = GetObject(result, "thread");
                    string threadId = GetString(thread, "id");
                    if (pending.autoStart && !String.IsNullOrWhiteSpace(threadId))
                    {
                        RouteData route = ChooseRoute(String.Empty);
                        if (IsObservedRoute(route))
                        {
                            SetThreadAuto(threadId, true, route);
                            changed = RewriteThreadResult(result, threadId) || changed;
                        }
                    }
                }
                else if (pending.method == "thread/read" || pending.method == "thread/resume")
                {
                    Dictionary<string, object> thread = GetObject(result, "thread");
                    string threadId = GetString(thread, "id");
                    if (IsThreadAuto(threadId))
                    {
                        changed = RewriteThreadResult(result, threadId) || changed;
                    }
                }
                else if (pending.method == "thread/list")
                {
                    IList threads = GetArray(result, "data");
                    if (threads != null)
                    {
                        foreach (object item in threads)
                        {
                            Dictionary<string, object> thread = item as Dictionary<string, object>;
                            string threadId = GetString(thread, "id");
                            if (IsThreadAuto(threadId))
                            {
                                changed = RewriteThread(thread, threadId) || changed;
                            }
                        }
                    }
                }
            }

            string method = GetString(message, "method");
            Dictionary<string, object> parameters = GetObject(message, "params");
            if (method == "thread/started" && parameters != null)
            {
                Dictionary<string, object> thread = GetObject(parameters, "thread");
                string threadId = GetString(thread, "id");
                if (!String.IsNullOrWhiteSpace(threadId) && IsThreadAuto(threadId))
                {
                    RouteData route = GetLastRoute(threadId) ?? ChooseRoute(String.Empty);
                    SetThreadAuto(threadId, true, route);
                    changed = RewriteThread(thread, threadId) || changed;
                }
            }
            else if (method == "thread/settings/updated" && parameters != null)
            {
                string threadId = GetString(parameters, "threadId");
                if (IsThreadAuto(threadId))
                {
                    Dictionary<string, object> settings = GetObject(parameters, "threadSettings");
                    if (settings != null)
                    {
                        RouteData route = GetLastRoute(threadId);
                        settings["model"] = VirtualModel;
                        if (route != null)
                        {
                            settings["effort"] = route.effort;
                        }
                        changed = true;
                    }
                }
            }

            return changed ? Json.Serialize(message) : line;
        }

        private static bool AddAutoModel(Dictionary<string, object> result)
        {
            IList data = GetArray(result, "data");
            if (data == null)
            {
                return false;
            }

            Dictionary<string, object> template = null;
            List<object> models = new List<object>();
            lock (CatalogGate)
            {
                AvailableModels.Clear();
                AvailableEfforts.Clear();
                foreach (object item in data)
                {
                    Dictionary<string, object> model = item as Dictionary<string, object>;
                    string modelId = GetString(model, "model");
                    if (!String.IsNullOrWhiteSpace(modelId) && !IsVirtual(modelId))
                    {
                        AvailableModels.Add(modelId);
                        HashSet<string> efforts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                        IList advertisedEfforts = GetArray(model, "supportedReasoningEfforts");
                        if (advertisedEfforts != null)
                        {
                            foreach (object effortItem in advertisedEfforts)
                            {
                                Dictionary<string, object> effort = effortItem as Dictionary<string, object>;
                                string effortName = GetString(effort, "reasoningEffort");
                                if (!String.IsNullOrWhiteSpace(effortName)) efforts.Add(effortName);
                            }
                        }
                        AvailableEfforts[modelId] = efforts;
                        if (template == null || modelId == "gpt-5.6-luna")
                        {
                            template = model;
                        }
                        object isDefault;
                        if (model.TryGetValue("isDefault", out isDefault) && isDefault is bool && (bool)isDefault)
                        {
                            CatalogDefaultModel = modelId;
                        }
                        models.Add(model);
                    }
                }
            }

            if (template == null)
            {
                return false;
            }
            Dictionary<string, object> auto = new Dictionary<string, object>(template);
            auto["id"] = VirtualModel;
            auto["model"] = VirtualModel;
            auto["displayName"] = VirtualDisplayName;
            auto["description"] = VirtualDescription;
            auto["hidden"] = false;
            auto["isDefault"] = GetDefaultAuto();
            auto["availabilityNux"] = new Dictionary<string, object> { { "message", VirtualDescription } };
            auto["defaultReasoningEffort"] = "low";
            if (GetDefaultAuto())
            {
                foreach (object item in models)
                {
                    Dictionary<string, object> model = item as Dictionary<string, object>;
                    if (model != null)
                    {
                        model["isDefault"] = false;
                    }
                }
            }
            models.Insert(0, auto);
            result["data"] = new ArrayList(models);
            return true;
        }

        private static bool HandleConfigWrite(Dictionary<string, object> edit)
        {
            if (!String.Equals(GetString(edit, "keyPath"), "model", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
            string value = GetString(edit, "value");
            if (IsVirtual(value))
            {
                SetDefaultAuto(true);
                edit["value"] = ChooseRoute(String.Empty).model;
                return true;
            }
            if (!String.IsNullOrWhiteSpace(value))
            {
                SetDefaultAuto(false);
            }
            return false;
        }

        private static bool RewriteConfigRead(Dictionary<string, object> result)
        {
            if (!GetDefaultAuto())
            {
                return false;
            }
            Dictionary<string, object> config = GetObject(result, "config");
            if (config == null)
            {
                return false;
            }
            config["model"] = VirtualModel;
            return true;
        }

        private static bool RewriteThreadResult(Dictionary<string, object> result, string threadId)
        {
            bool changed = false;
            Dictionary<string, object> thread = GetObject(result, "thread");
            changed = RewriteThread(thread, threadId) || changed;
            if (result.ContainsKey("model"))
            {
                result["model"] = VirtualModel;
                changed = true;
            }
            RouteData route = GetLastRoute(threadId);
            if (route != null && result.ContainsKey("reasoningEffort"))
            {
                result["reasoningEffort"] = route.effort;
                changed = true;
            }
            return changed;
        }

        private static bool RewriteThread(Dictionary<string, object> thread, string threadId)
        {
            if (thread == null || !IsThreadAuto(threadId))
            {
                return false;
            }
            bool changed = false;
            if (thread.ContainsKey("model"))
            {
                thread["model"] = VirtualModel;
                changed = true;
            }
            return changed;
        }

        private static void SetThreadStartEffort(Dictionary<string, object> parameters, string effort)
        {
            Dictionary<string, object> config = GetObject(parameters, "config");
            if (config == null)
            {
                config = new Dictionary<string, object>();
                parameters["config"] = config;
            }
            config["model_reasoning_effort"] = effort;
        }

        private static void RewriteCollaborationMode(Dictionary<string, object> parameters, RouteData route)
        {
            Dictionary<string, object> collaboration = GetObject(parameters, "collaborationMode");
            Dictionary<string, object> settings = GetObject(collaboration, "settings");
            if (settings != null)
            {
                settings["model"] = route.model;
                settings["reasoning_effort"] = route.effort;
            }
        }

        private static string ExtractTaskText(IList input)
        {
            if (input == null)
            {
                return String.Empty;
            }
            StringBuilder text = new StringBuilder();
            foreach (object item in input)
            {
                Dictionary<string, object> part = item as Dictionary<string, object>;
                if (part != null && GetString(part, "type") == "text")
                {
                    if (text.Length > 0) text.Append('\n');
                    text.Append(GetString(part, "text"));
                }
            }
            return text.ToString();
        }

        private static RouteData ChooseRoute(string taskText, bool ultraApproved = false, bool forceUltraCandidate = false)
        {
            string normalized = (taskText ?? String.Empty).ToLowerInvariant();
            string tier = normalized.Length == 0 ? "fast" : "balanced";
            string effort = normalized.Length == 0 ? "low" : "medium";
            bool requiresUltraApproval = false;

            string[] deepSignals =
            {
                "architecture", "large refactor", "root cause", "complex debugging", "benchmark", "multi-step",
                "whole project", "ทั้งระบบ", "สถาปัตยกรรม", "รีแฟกเตอร์", "หาสาเหตุ",
                "แก้บั๊กซับซ้อน", "หลายขั้นตอน", "ตรวจทั้งโปรเจกต์"
            };
            string[] criticalSignals =
            {
                "production", "deploy", "security", "vulnerability", "authentication", "authorization",
                "payment", "database migration", "schema migration", "incident", "release", "compliance",
                "audit", "real money", "customer data", "ระบบจริง", "โปรดักชัน", "ดีพลอย",
                "ความปลอดภัย", "ช่องโหว่", "ยืนยันตัวตน", "กำหนดสิทธิ์", "ชำระเงิน",
                "ไมเกรตฐานข้อมูล", "ย้ายฐานข้อมูล", "เหตุขัดข้อง", "รีลีส", "กำกับดูแล",
                "ตรวจสอบระบบ", "เงินจริง", "ข้อมูลลูกค้า"
            };
            string[] ultraSignals =
            {
                "multi-agent", "multi agent", "whole codebase", "mission critical", "critical incident",
                "major migration", "largest", "หลายเอเจนต์", "มอบงานหลาย", "ทั้งโค้ดเบส",
                "ทั้ง codebase", "ภารกิจใหญ่", "วิกฤต", "ย้ายระบบครั้งใหญ่"
            };
            string[] fastSignals =
            {
                "translate", "summarize", "rewrite", "short answer", "status only", "list files", "find file",
                "read only", "quick question", "แปล", "สรุป", "เขียนใหม่", "ตอบสั้น", "เช็คสถานะ",
                "ดูสถานะ", "รายชื่อไฟล์", "หาไฟล์", "อ่านอย่างเดียว", "คำถามสั้น"
            };

            PolicyData policy;
            string policyHash;
            string policyReason;
            if (!TryLoadPolicy(out policy, out policyHash, out policyReason)) policy = null;
            deepSignals = GetPolicySignals(policy, "deep", deepSignals);
            criticalSignals = GetPolicySignals(policy, "critical", criticalSignals);
            ultraSignals = GetPolicySignals(policy, "ultra", ultraSignals);
            fastSignals = GetPolicySignals(policy, "fast", fastSignals);
            int fastMaxChars = policy == null ? 1400 : policy.thresholds.fast_max_chars;
            int deepMinChars = policy == null ? 4000 : policy.thresholds.deep_min_chars;
            int ultraMinChars = policy == null ? 10000 : policy.thresholds.ultra_min_chars;
            effort = GetPolicyEffort(policy, tier, effort, false);

            bool ultraCandidate = forceUltraCandidate || normalized.Length > ultraMinChars || ContainsAny(normalized, ultraSignals);
            if (ultraCandidate)
            {
                tier = "ultra_pending";
                effort = GetPolicyEffort(policy, "ultra", "high", true);
                requiresUltraApproval = !ultraApproved;
            }
            else if (ContainsAny(normalized, criticalSignals))
            {
                tier = "critical";
                effort = GetPolicyEffort(policy, "critical", "high", false);
            }
            else if (normalized.Length > deepMinChars || ContainsAny(normalized, deepSignals))
            {
                tier = "deep";
                effort = GetPolicyEffort(policy, "deep", "high", false);
            }
            else if (normalized.Length > 0 && normalized.Length < fastMaxChars && ContainsAny(normalized, fastSignals))
            {
                tier = "fast";
                effort = GetPolicyEffort(policy, "fast", "low", false);
            }

            string[] preferences;
            if (tier == "ultra_pending")
            {
                preferences = GetPolicyModels(policy, "ultra", new[] { "gpt-5.6-sol", "gpt-5.6-terra" });
            }
            else if (tier == "critical")
            {
                preferences = GetPolicyModels(policy, "critical", new[] { "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna" });
            }
            else if (tier == "deep")
            {
                preferences = GetPolicyModels(policy, "deep", new[] { "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.6-luna" });
            }
            else if (tier == "fast")
            {
                preferences = GetPolicyModels(policy, "fast", new[] { "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol" });
            }
            else
            {
                preferences = GetPolicyModels(policy, "balanced", new[] { "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol" });
            }

            string selected = null;
            bool selectedObserved = false;
            lock (CatalogGate)
            {
                foreach (string candidate in preferences)
                {
                    if (AvailableModels.Contains(candidate) && !IsManualOnlyModel(policy, candidate))
                    {
                        selected = candidate;
                        break;
                    }
                }
                if (selected == null)
                {
                    string environmentFallback = Environment.GetEnvironmentVariable("KIMMIZO_AUTO_FALLBACK");
                    if (!String.IsNullOrWhiteSpace(environmentFallback) && AvailableModels.Contains(environmentFallback) &&
                        !IsManualOnlyModel(policy, environmentFallback))
                    {
                        selected = environmentFallback;
                    }
                }
                selectedObserved = !String.IsNullOrWhiteSpace(selected) && AvailableModels.Contains(selected);
            }
            if (ultraCandidate && ultraApproved)
            {
                if (SupportsEffort(selected, "ultra"))
                {
                    tier = "ultra";
                    effort = GetPolicyEffort(policy, "ultra", "ultra", false);
                    requiresUltraApproval = false;
                }
                else
                {
                    tier = "ultra_unavailable";
                    effort = "high";
                    requiresUltraApproval = false;
                }
            }
            return new RouteData
            {
                model = selected,
                effort = effort,
                tier = tier,
                requiresUltraApproval = requiresUltraApproval,
                modelObserved = selectedObserved
            };
        }

        private static bool IsObservedRoute(RouteData route)
        {
            if (route == null || !route.modelObserved || String.IsNullOrWhiteSpace(route.model)) return false;
            lock (CatalogGate)
            {
                return AvailableModels.Contains(route.model);
            }
        }

        // Keep the concrete model stable within a work phase so Codex can reuse its prompt cache.
        // A new task phase or a genuinely stronger requirement may still change the route.
        private static RouteData ChooseAdaptiveRoute(RouteData currentRoute, string taskText, bool ultraApproved = false, bool forceUltraCandidate = false)
        {
            RouteData candidate = ChooseRoute(taskText, ultraApproved, forceUltraCandidate);
            if (!IsObservedRoute(candidate) || currentRoute == null || !IsObservedRoute(currentRoute) || IsNewWorkPhase(taskText))
            {
                return candidate;
            }
            if (ultraApproved || candidate.requiresUltraApproval || IsStrongerRoute(candidate, currentRoute))
            {
                return candidate;
            }
            return currentRoute;
        }

        private static bool IsNewWorkPhase(string taskText)
        {
            string normalized = (taskText ?? String.Empty).ToLowerInvariant();
            return ContainsAny(normalized, new[]
            {
                "เริ่มงานใหม่", "งานใหม่:", "รีเซ็ต auto", "reset auto", "new task:", "new task "
            });
        }

        private static bool IsStrongerRoute(RouteData candidate, RouteData current)
        {
            if (candidate == null) return false;
            if (current == null) return true;
            int candidateModel = ModelRank(candidate.model, candidate.tier);
            int currentModel = ModelRank(current.model, current.tier);
            if (candidateModel != currentModel)
            {
                return candidateModel > currentModel;
            }
            return EffortRank(candidate.effort) > EffortRank(current.effort);
        }

        private static int ModelRank(string model, string tier)
        {
            if (String.Equals(model, "gpt-6-astra", StringComparison.OrdinalIgnoreCase)) return 4;
            if (String.Equals(model, "gpt-5.6-sol", StringComparison.OrdinalIgnoreCase)) return 3;
            if (String.Equals(model, "gpt-5.6-terra", StringComparison.OrdinalIgnoreCase)) return 2;
            if (String.Equals(model, "gpt-5.6-luna", StringComparison.OrdinalIgnoreCase)) return 1;
            if (tier == "ultra" || tier == "ultra_pending") return 3;
            if (tier == "critical") return 3;
            if (tier == "deep") return 2;
            return 1;
        }

        private static int EffortRank(string effort)
        {
            if (String.Equals(effort, "ultra", StringComparison.OrdinalIgnoreCase)) return 5;
            if (String.Equals(effort, "xhigh", StringComparison.OrdinalIgnoreCase)) return 4;
            if (String.Equals(effort, "high", StringComparison.OrdinalIgnoreCase)) return 3;
            if (String.Equals(effort, "medium", StringComparison.OrdinalIgnoreCase)) return 2;
            return 1;
        }

        private static bool SupportsEffort(string model, string effort)
        {
            lock (CatalogGate)
            {
                HashSet<string> efforts;
                if (AvailableEfforts.TryGetValue(model, out efforts))
                {
                    return efforts.Contains(effort);
                }
            }
            return String.Equals(model, "gpt-5.6-sol", StringComparison.OrdinalIgnoreCase)
                || String.Equals(model, "gpt-5.6-terra", StringComparison.OrdinalIgnoreCase);
        }

        private static bool ContainsAny(string text, IEnumerable<string> values)
        {
            foreach (string value in values)
            {
                if (text.IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return true;
                }
            }
            return false;
        }

        private static string NormalizeIntentText(string text)
        {
            StringBuilder normalized = new StringBuilder();
            bool pendingSpace = false;
            foreach (char character in (text ?? String.Empty))
            {
                if (character == '\'' || character == '\u2019') continue;
                if (Char.IsLetterOrDigit(character))
                {
                    if (pendingSpace && normalized.Length > 0) normalized.Append(' ');
                    normalized.Append(Char.ToLowerInvariant(character));
                    pendingSpace = false;
                }
                else if (normalized.Length > 0)
                {
                    pendingSpace = true;
                }
            }
            return normalized.ToString();
        }

        private static bool ContainsIntentPhrase(string normalizedText, string phrase)
        {
            string normalizedPhrase = NormalizeIntentText(phrase);
            if (String.IsNullOrWhiteSpace(normalizedPhrase)) return false;
            return normalizedText == normalizedPhrase ||
                normalizedText.StartsWith(normalizedPhrase + " ", StringComparison.Ordinal) ||
                normalizedText.EndsWith(" " + normalizedPhrase, StringComparison.Ordinal) ||
                normalizedText.IndexOf(" " + normalizedPhrase + " ", StringComparison.Ordinal) >= 0;
        }

        private static bool IsUltraApproval(string text)
        {
            string normalized = NormalizeIntentText(text);
            foreach (string phrase in new[] { "อนุมัติ", "ยืนยัน", "ใช้ ultra", "เปิด ultra", "approve ultra", "approve" })
            {
                if (ContainsIntentPhrase(normalized, phrase)) return true;
            }
            return false;
        }

        private static bool IsUltraDenial(string text)
        {
            string normalized = NormalizeIntentText(text);
            foreach (string phrase in new[]
            {
                "ไม่อนุมัติ", "ไม่ใช้ ultra", "ไม่เอา ultra", "deny ultra", "decline ultra",
                "do not approve ultra", "dont approve ultra", "not approve ultra", "ปฏิเสธ ultra", "ไม่ต้อง"
            })
            {
                if (ContainsIntentPhrase(normalized, phrase)) return true;
            }
            return false;
        }

        private static bool IsUltraApprovalOnly(string text)
        {
            return IsOnlyUltraIntent(text, new[] { "อนุมัติ", "ยืนยัน", "ใช้ ultra", "เปิด ultra", "approve ultra", "approve" });
        }

        private static bool IsUltraDenialOnly(string text)
        {
            return IsOnlyUltraIntent(text, new[]
            {
                "ไม่อนุมัติ", "ไม่ใช้ ultra", "ไม่เอา ultra", "deny ultra", "decline ultra",
                "do not approve ultra", "dont approve ultra", "not approve ultra", "ปฏิเสธ ultra", "ไม่ต้อง"
            });
        }

        private static bool IsOnlyUltraIntent(string text, IEnumerable<string> phrases)
        {
            string normalized = NormalizeIntentText(text);
            if (String.IsNullOrWhiteSpace(normalized)) return false;
            foreach (string phrase in phrases)
            {
                if (String.Equals(normalized, NormalizeIntentText(phrase), StringComparison.Ordinal)) return true;
            }
            return false;
        }

        private static bool AddUltraApprovalContext(Dictionary<string, object> parameters)
        {
            Dictionary<string, object> additional;
            if (!TryGetAdditionalContext(parameters, out additional)) return false;
            additional["kimmizo_auto_ultra_approval"] = new Dictionary<string, object>
            {
                { "kind", "application" },
                { "value", "งานนี้อาจเหมาะกับ Ultra แต่ยังไม่ได้รับอนุมัติ ห้ามเริ่มงานสาระสำคัญ ให้ถามบอสเป็นภาษาไทยก่อนว่าอนุมัติให้ใช้ Ultra หรือไม่ พร้อมบอกเหตุผลสั้น ๆ" }
            };
            return true;
        }

        private static bool TryLoadPolicy(out PolicyData policy, out string policyHash, out string reason)
        {
            policy = null;
            policyHash = null;
            reason = null;
            try
            {
                if (!File.Exists(PolicyPath))
                {
                    reason = "The shared Auto model policy is missing.";
                    return false;
                }
                byte[] policyBytes = File.ReadAllBytes(PolicyPath);
                policyHash = ComputeSha256(policyBytes);
                if (!File.Exists(PolicyHashPath))
                {
                    reason = "The shared Auto model policy hash stamp is missing.";
                    return false;
                }
                string expectedHash = File.ReadAllText(PolicyHashPath, Encoding.UTF8).Trim();
                if (!String.Equals(policyHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                {
                    reason = "The shared Auto model policy hash does not match its hash stamp.";
                    return false;
                }
                policy = Json.Deserialize<PolicyData>(File.ReadAllText(PolicyPath, Encoding.UTF8));
                if (!ValidatePolicy(policy, out reason))
                {
                    policy = null;
                    return false;
                }
                return true;
            }
            catch (Exception error)
            {
                policy = null;
                reason = "The shared Auto model policy could not be verified: " + error.Message;
                return false;
            }
        }

        private static bool ValidatePolicy(PolicyData policy, out string reason)
        {
            reason = null;
            if (policy == null || policy.schema_version != PolicySchemaVersion)
            {
                reason = "The shared Auto model policy schema is unsupported.";
                return false;
            }
            if (policy.policy_version != PolicyVersion || policy.usage_policy == null || policy.model_selection == null || policy.thresholds == null || policy.voice == null)
            {
                reason = "The shared Auto model policy is incomplete.";
                return false;
            }
            UsagePolicyData usage = policy.usage_policy;
            if (usage.mode != "chatgpt_plus_limit_first" || usage.default_model != "gpt-5.6-luna" ||
                usage.default_effort != "low" || usage.automatic_multi_agent || usage.fast_mode ||
                usage.execution_mode != "serial" || !usage.verify_before_escalation ||
                usage.manual_only_models == null || usage.manual_only_models.Count != 1 ||
                !String.Equals(usage.manual_only_models[0], "gpt-6-astra", StringComparison.OrdinalIgnoreCase) ||
                usage.escalation_order == null || usage.escalation_order.Count != 4)
            {
                reason = "The shared Auto model usage policy is invalid.";
                return false;
            }
            string[] expectedEscalation = { "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra" };
            for (int index = 0; index < expectedEscalation.Length; index++)
            {
                if (!String.Equals(usage.escalation_order[index], expectedEscalation[index], StringComparison.OrdinalIgnoreCase))
                {
                    reason = "The shared Auto model escalation order is invalid.";
                    return false;
                }
            }
            HashSet<string> automaticModels = new HashSet<string>(new[]
            {
                "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"
            }, StringComparer.OrdinalIgnoreCase);
            foreach (string tier in new[] { "fast", "balanced", "deep", "critical", "ultra" })
            {
                ModelPolicyData route;
                if (!policy.model_selection.TryGetValue(tier, out route) || route == null ||
                    String.IsNullOrWhiteSpace(route.effort) || route.models == null || route.models.Count == 0 || route.signals == null)
                {
                    reason = "The shared Auto model policy has an incomplete " + tier + " route.";
                    return false;
                }
                foreach (string model in route.models)
                {
                    if (!automaticModels.Contains(model) || IsManualOnlyModel(policy, model))
                    {
                        reason = "The shared Auto model policy contains a non-automatic model in the " + tier + " route.";
                        return false;
                    }
                }
            }
            if (!policy.model_selection["ultra"].requires_approval)
            {
                reason = "The shared Auto model policy must require approval for Ultra.";
                return false;
            }
            if (policy.thresholds.fast_max_chars <= 0 ||
                policy.thresholds.deep_min_chars <= 0 ||
                policy.thresholds.ultra_min_chars <= 0)
            {
                reason = "The shared Auto model policy thresholds are invalid.";
                return false;
            }
            if (policy.voice.trigger != PolicyTrigger || policy.voice.pronoun != "ฉัน" || policy.voice.suffix != "ค่ะ" ||
                String.IsNullOrWhiteSpace(policy.voice.instruction) || policy.voice.blocked_message != FixedVoiceBlockedMessage)
            {
                reason = "The shared Auto model policy voice contract is invalid.";
                return false;
            }
            return true;
        }

        private static bool IsManualOnlyModel(PolicyData policy, string model)
        {
            if (String.Equals(model, "gpt-6-astra", StringComparison.OrdinalIgnoreCase)) return true;
            if (policy == null || policy.usage_policy == null || policy.usage_policy.manual_only_models == null) return false;
            foreach (string manualOnly in policy.usage_policy.manual_only_models)
            {
                if (String.Equals(model, manualOnly, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        private static ModelPolicyData GetPolicyRoute(PolicyData policy, string tier)
        {
            if (policy == null || policy.model_selection == null) return null;
            ModelPolicyData route;
            return policy.model_selection.TryGetValue(tier, out route) ? route : null;
        }

        private static string[] GetPolicySignals(PolicyData policy, string tier, string[] fallback)
        {
            ModelPolicyData route = GetPolicyRoute(policy, tier);
            return route == null || route.signals == null || route.signals.Count == 0
                ? fallback
                : route.signals.ToArray();
        }

        private static string[] GetPolicyModels(PolicyData policy, string tier, string[] fallback)
        {
            ModelPolicyData route = GetPolicyRoute(policy, tier);
            return route == null || route.models == null || route.models.Count == 0
                ? fallback
                : route.models.ToArray();
        }

        private static string GetPolicyEffort(PolicyData policy, string tier, string fallback, bool pending)
        {
            ModelPolicyData route = GetPolicyRoute(policy, tier);
            if (route == null) return fallback;
            if (pending && !String.IsNullOrWhiteSpace(route.pending_effort)) return route.pending_effort;
            return String.IsNullOrWhiteSpace(route.effort) ? fallback : route.effort;
        }

        private static string ComputeSha256(byte[] bytes)
        {
            using (SHA256 sha256 = SHA256.Create())
            {
                byte[] digest = sha256.ComputeHash(bytes ?? new byte[0]);
                StringBuilder result = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest)
                {
                    result.Append(value.ToString("x2", CultureInfo.InvariantCulture));
                }
                return result.ToString();
            }
        }

        private static bool TryLoadVoiceBootstrap(out VoiceBootstrapData bootstrap, out string status, out string reason)
        {
            bootstrap = null;
            status = "unverified";
            reason = null;

            PolicyData policy;
            string policyHash;
            if (!TryLoadPolicy(out policy, out policyHash, out reason))
            {
                return false;
            }

            string projectRoot = GetProjectCapsuleRoot();
            List<string> candidates = GetVoiceBootstrapCandidates(projectRoot);
            bool found = false;
            foreach (string candidatePath in candidates)
            {
                if (!File.Exists(candidatePath)) continue;
                found = true;
                try
                {
                    bool projectCandidate = IsProjectVoiceBootstrapCandidate(projectRoot, candidatePath);
                    byte[] sidecarBytes = File.ReadAllBytes(candidatePath);
                    if (projectCandidate)
                    {
                        ProjectCapsuleManifestData manifest;
                        string manifestReason;
                        if (!TryLoadProjectCapsuleManifest(projectRoot, sidecarBytes, policyHash, out manifest, out manifestReason))
                        {
                            reason = manifestReason;
                            return false;
                        }
                    }
                    VoiceBootstrapData candidate = Json.Deserialize<VoiceBootstrapData>(
                        Encoding.UTF8.GetString(sidecarBytes));
                    if (candidate == null)
                    {
                        reason = "The voice bootstrap sidecar is empty.";
                        return false;
                    }
                    if (candidate.schemaVersion != PolicySchemaVersion)
                    {
                        reason = "The voice bootstrap sidecar schema is unsupported.";
                        return false;
                    }
                    if (String.IsNullOrWhiteSpace(candidate.policyVersion) || String.IsNullOrWhiteSpace(candidate.policySha256) ||
                        String.IsNullOrWhiteSpace(candidate.trigger) || String.IsNullOrWhiteSpace(candidate.pronoun) ||
                        String.IsNullOrWhiteSpace(candidate.suffix) || String.IsNullOrWhiteSpace(candidate.instruction) ||
                        String.IsNullOrWhiteSpace(candidate.blockedMessage))
                    {
                        reason = "The voice bootstrap sidecar is missing a required invariant.";
                        return false;
                    }
                    if (!String.Equals(candidate.policyVersion, policy.policy_version, StringComparison.Ordinal) ||
                        !String.Equals(candidate.policySha256, policyHash, StringComparison.OrdinalIgnoreCase) ||
                        candidate.trigger != policy.voice.trigger || candidate.pronoun != policy.voice.pronoun ||
                        candidate.suffix != policy.voice.suffix || candidate.instruction != policy.voice.instruction ||
                        candidate.blockedMessage != policy.voice.blocked_message)
                    {
                        reason = "The voice bootstrap sidecar does not match the verified Auto policy.";
                        return false;
                    }
                    candidate.source = projectCandidate ? "project" : "global";
                    bootstrap = candidate;
                    status = "configured";
                    return true;
                }
                catch (Exception error)
                {
                    reason = "The voice bootstrap sidecar could not be verified: " + error.Message;
                    return false;
                }
            }
            reason = found ? "The voice bootstrap sidecar is invalid." : "The voice bootstrap sidecar was not found.";
            return false;
        }

        private static bool TryLoadProjectCapsuleManifest(string projectRoot, byte[] sidecarBytes, string policyHash, out ProjectCapsuleManifestData manifest, out string reason)
        {
            manifest = null;
            reason = null;
            try
            {
                if (String.IsNullOrWhiteSpace(projectRoot))
                {
                    reason = "The project capsule root is unavailable.";
                    return false;
                }
                string manifestPath = Path.Combine(projectRoot, ".kimmizo", "core", "manifest.json");
                if (!File.Exists(manifestPath))
                {
                    reason = "The project capsule manifest is missing.";
                    return false;
                }
                ProjectCapsuleManifestData candidate = Json.Deserialize<ProjectCapsuleManifestData>(
                    File.ReadAllText(manifestPath, Encoding.UTF8));
                if (!ValidateProjectCapsuleManifest(candidate, sidecarBytes, policyHash, out reason))
                {
                    return false;
                }
                manifest = candidate;
                return true;
            }
            catch (Exception error)
            {
                reason = "The project capsule manifest could not be verified: " + error.Message;
                return false;
            }
        }

        private static bool ValidateProjectCapsuleManifest(ProjectCapsuleManifestData manifest, byte[] sidecarBytes, string policyHash, out string reason)
        {
            reason = null;
            if (manifest == null || manifest.schema != ProjectCapsuleSchema)
            {
                reason = "The project capsule manifest schema is unsupported.";
                return false;
            }
            if (manifest.schema_version != ProjectCapsuleSchemaVersion)
            {
                reason = "The project capsule manifest has an unknown major schema version.";
                return false;
            }
            if (!IsCanonicalProjectId(manifest.project_id) ||
                String.IsNullOrWhiteSpace(manifest.capsule_version) ||
                String.IsNullOrWhiteSpace(manifest.core_version) ||
                String.IsNullOrWhiteSpace(manifest.adapter_version) ||
                !IsSha256(manifest.source_revision) ||
                !IsCapsuleRevision(manifest.active_revision, manifest.source_revision))
            {
                reason = "The project capsule manifest is missing a required project or capsule invariant.";
                return false;
            }
            if (manifest.lifecycle != "active" || manifest.provenance != ProjectCapsuleProvenance ||
                manifest.compatibility == null || manifest.compatibility.minimum_setup_version != ProjectCapsuleMinimumSetupVersion)
            {
                reason = "The project capsule manifest is not active or has an unsupported provenance.";
                return false;
            }
            if (manifest.previous_revision != null && !IsCapsuleRevision(manifest.previous_revision, null))
            {
                reason = "The project capsule manifest previous revision is invalid.";
                return false;
            }
            if (!IsSha256(manifest.aggregate_sha256) || !IsSha256(manifest.bootstrap_sha256) ||
                !IsSha256(manifest.policy_sha256) || !IsSha256(manifest.migration_sha256) ||
                !IsSha256(manifest.agents_block_sha256) ||
                !String.Equals(manifest.bootstrap_hash, manifest.bootstrap_sha256, StringComparison.Ordinal) ||
                !String.Equals(manifest.policy_sha256, policyHash, StringComparison.Ordinal))
            {
                reason = "The project capsule manifest hash contract is invalid.";
                return false;
            }
            if (manifest.file_hashes == null || manifest.file_hashes.Count == 0)
            {
                reason = "The project capsule manifest file hashes are missing.";
                return false;
            }
            foreach (KeyValuePair<string, string> entry in manifest.file_hashes)
            {
                if (!IsSafeCapsuleRelativePath(entry.Key) || !IsSha256(entry.Value))
                {
                    reason = "The project capsule manifest file hashes are invalid.";
                    return false;
                }
            }
            string listedBootstrapHash;
            if (!manifest.file_hashes.TryGetValue(ProjectVoiceBootstrapRelativePath, out listedBootstrapHash) ||
                !String.Equals(listedBootstrapHash, manifest.bootstrap_sha256, StringComparison.Ordinal) ||
                !String.Equals(ComputeCapsuleAggregateHash(manifest.file_hashes), manifest.aggregate_sha256, StringComparison.Ordinal) ||
                !String.Equals(ComputeCapsuleSourceRevision(manifest.aggregate_sha256, manifest.agents_block_sha256, manifest.policy_sha256), manifest.source_revision, StringComparison.Ordinal))
            {
                reason = "The project capsule manifest integrity contract is invalid.";
                return false;
            }
            if (!String.Equals(ComputeSha256(sidecarBytes), manifest.bootstrap_sha256, StringComparison.Ordinal))
            {
                reason = "The project voice bootstrap bytes do not match the capsule manifest.";
                return false;
            }
            return true;
        }

        private static bool IsProjectVoiceBootstrapCandidate(string projectRoot, string candidatePath)
        {
            if (String.IsNullOrWhiteSpace(projectRoot) || String.IsNullOrWhiteSpace(candidatePath)) return false;
            try
            {
                string expected = Path.GetFullPath(Path.Combine(projectRoot, ".kimmizo", VoiceBootstrapFileName));
                return String.Equals(Path.GetFullPath(candidatePath), expected, StringComparison.OrdinalIgnoreCase);
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static bool IsCanonicalProjectId(string value)
        {
            Guid parsed;
            return !String.IsNullOrWhiteSpace(value) && Guid.TryParse(value, out parsed) &&
                String.Equals(parsed.ToString("D"), value.ToLowerInvariant(), StringComparison.Ordinal);
        }

        private static bool IsSha256(string value)
        {
            if (String.IsNullOrWhiteSpace(value) || value.Length != 64) return false;
            foreach (char character in value)
            {
                if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            }
            return true;
        }

        private static bool IsCapsuleRevision(string value, string sourceRevision)
        {
            if (String.IsNullOrWhiteSpace(value) || !value.StartsWith("v2-", StringComparison.Ordinal)) return false;
            string[] pieces = value.Split('-');
            if ((pieces.Length != 2 && pieces.Length != 3) || !IsLowerHex(pieces[1], 16) ||
                (pieces.Length == 3 && !IsLowerHex(pieces[2], 8))) return false;
            return String.IsNullOrWhiteSpace(sourceRevision) ||
                String.Equals(pieces[1], sourceRevision.Substring(0, 16), StringComparison.Ordinal);
        }

        private static bool IsLowerHex(string value, int length)
        {
            if (String.IsNullOrWhiteSpace(value) || value.Length != length) return false;
            foreach (char character in value)
            {
                if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f'))) return false;
            }
            return true;
        }

        private static bool IsSafeCapsuleRelativePath(string value)
        {
            if (String.IsNullOrWhiteSpace(value) || value.IndexOf('\\') >= 0 || value.StartsWith("/", StringComparison.Ordinal) || value.IndexOf(':') >= 0) return false;
            foreach (string segment in value.Split('/'))
            {
                if (String.IsNullOrWhiteSpace(segment) || segment == "." || segment == "..") return false;
            }
            return true;
        }

        private static string ComputeCapsuleAggregateHash(Dictionary<string, string> fileHashes)
        {
            StringBuilder payload = new StringBuilder();
            foreach (string relative in fileHashes.Keys.OrderBy(value => value, StringComparer.Ordinal))
            {
                payload.Append(relative).Append(':').Append(fileHashes[relative]).Append('\n');
            }
            return ComputeSha256(Encoding.UTF8.GetBytes(payload.ToString()));
        }

        private static string ComputeCapsuleSourceRevision(string aggregateHash, string agentsBlockHash, string policyHash)
        {
            return ComputeSha256(Encoding.ASCII.GetBytes(aggregateHash + "\n" + agentsBlockHash + "\n" + policyHash + "\n"));
        }

        private static List<string> GetVoiceBootstrapCandidates(string projectRoot)
        {
            List<string> candidates = new List<string>();
            if (!String.IsNullOrWhiteSpace(projectRoot))
            {
                AddVoiceBootstrapCandidate(candidates, Path.Combine(projectRoot, ".kimmizo", VoiceBootstrapFileName));
                return candidates;
            }
            AddVoiceBootstrapCandidate(candidates, Path.Combine(InstallRoot, VoiceBootstrapFileName));
            return candidates;
        }

        private static string GetProjectCapsuleRoot()
        {
            string configuredRoot = Environment.GetEnvironmentVariable("KIMMIZO_PROJECT_ROOT");
            if (!String.IsNullOrWhiteSpace(configuredRoot))
            {
                try
                {
                    return Path.GetFullPath(configuredRoot);
                }
                catch (Exception)
                {
                    return configuredRoot;
                }
            }

            string current = Directory.GetCurrentDirectory();
            while (!String.IsNullOrWhiteSpace(current))
            {
                string marker = Path.Combine(current, ".kimmizo", "core", "manifest.json");
                if (File.Exists(marker)) return current;
                DirectoryInfo directory = new DirectoryInfo(current);
                DirectoryInfo parent = directory.Parent;
                if (parent == null) break;
                current = parent.FullName;
            }
            return null;
        }

        private static void AddVoiceBootstrapCandidate(List<string> candidates, string path)
        {
            try
            {
                string resolved = Path.GetFullPath(path);
                if (!candidates.Contains(resolved, StringComparer.OrdinalIgnoreCase)) candidates.Add(resolved);
            }
            catch (Exception)
            {
            }
        }

        private static bool IsSubstantiveWorkflow(string taskText)
        {
            return !String.IsNullOrWhiteSpace(taskText) && !IsUltraApprovalOnly(taskText) && !IsUltraDenialOnly(taskText);
        }

        private static bool InjectVoiceBootstrap(Dictionary<string, object> parameters, VoiceBootstrapData bootstrap)
        {
            if (parameters == null || bootstrap == null || String.IsNullOrWhiteSpace(bootstrap.instruction)) return false;
            Dictionary<string, object> additional;
            if (!TryGetAdditionalContext(parameters, out additional)) return false;
            additional["kimmizo_voice_bootstrap"] = new Dictionary<string, object>
            {
                { "kind", "application" },
                { "value", bootstrap.instruction }
            };
            return true;
        }

        private static bool TryGetAdditionalContext(Dictionary<string, object> parameters, out Dictionary<string, object> additional)
        {
            additional = null;
            if (parameters == null) return false;
            object existing;
            if (!parameters.TryGetValue("additionalContext", out existing) || existing == null)
            {
                additional = new Dictionary<string, object>();
                parameters["additionalContext"] = additional;
                return true;
            }
            additional = existing as Dictionary<string, object>;
            return additional != null;
        }

        private static string BuildVoiceBlockedResponse(object id)
        {
            Dictionary<string, object> error = new Dictionary<string, object>
            {
                { "code", VoiceBlockedCode },
                { "message", FixedVoiceBlockedMessage }
            };
            return Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", id },
                { "error", error }
            });
        }

        private static string BuildModelUnverifiedResponse(object id)
        {
            Dictionary<string, object> error = new Dictionary<string, object>
            {
                { "code", ModelUnverifiedCode },
                { "message", FixedModelUnverifiedMessage }
            };
            return Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", id },
                { "error", error }
            });
        }

        private static string BuildContextUnverifiedResponse(object id)
        {
            Dictionary<string, object> error = new Dictionary<string, object>
            {
                { "code", ContextUnverifiedCode },
                { "message", FixedContextUnverifiedMessage }
            };
            return Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", id },
                { "error", error }
            });
        }

        private static TransformResult BuildBlockedTransform(Dictionary<string, object> message, int code, string errorMessage)
        {
            object id;
            if (message == null || !message.TryGetValue("id", out id) || id == null)
            {
                return new TransformResult { ForwardLine = null, ImmediateResponse = null };
            }
            if (code == VoiceBlockedCode)
            {
                return new TransformResult { ImmediateResponse = BuildVoiceBlockedResponse(id), ForwardLine = null };
            }
            if (code == ContextUnverifiedCode)
            {
                return new TransformResult { ImmediateResponse = BuildContextUnverifiedResponse(id), ForwardLine = null };
            }
            return new TransformResult { ImmediateResponse = BuildModelUnverifiedResponse(id), ForwardLine = null };
        }

        private static void SetVoiceStatus(string status, string source, string policyVersion, string policySha256, string reason)
        {
            lock (StateGate)
            {
                if (State.voiceBootstrap == null) State.voiceBootstrap = new VoiceStateData();
                bool changed = State.voiceBootstrap.status != status || State.voiceBootstrap.source != source ||
                    State.voiceBootstrap.policyVersion != policyVersion || State.voiceBootstrap.policySha256 != policySha256 ||
                    State.voiceBootstrap.reason != reason;
                State.voiceBootstrap.status = status;
                State.voiceBootstrap.source = source;
                State.voiceBootstrap.policyVersion = policyVersion;
                State.voiceBootstrap.policySha256 = policySha256;
                State.voiceBootstrap.reason = reason;
                if (status == "configured" || status == "enforced") State.voiceBootstrap.verifiedAt = DateTime.UtcNow.ToString("o");
                if (changed) SaveStateLocked();
            }
        }

        private static Dictionary<string, object> GetVoiceStatus()
        {
            VoiceBootstrapData bootstrap;
            string status;
            string reason;
            if (TryLoadVoiceBootstrap(out bootstrap, out status, out reason))
            {
                bool keepEnforced = false;
                lock (StateGate)
                {
                    keepEnforced = State.voiceBootstrap != null && State.voiceBootstrap.status == "enforced" &&
                        State.voiceBootstrap.source == bootstrap.source && State.voiceBootstrap.policyVersion == bootstrap.policyVersion &&
                        String.Equals(State.voiceBootstrap.policySha256, bootstrap.policySha256, StringComparison.OrdinalIgnoreCase);
                }
                SetVoiceStatus(keepEnforced ? "enforced" : status, bootstrap.source, bootstrap.policyVersion, bootstrap.policySha256, null);
            }
            else
            {
                SetVoiceStatus("unverified", null, null, null, reason);
            }
            lock (StateGate)
            {
                VoiceStateData voice = State.voiceBootstrap ?? new VoiceStateData();
                return new Dictionary<string, object>
                {
                    { "status", voice.status },
                    { "source", voice.source },
                    { "policyVersion", voice.policyVersion },
                    { "policySha256", voice.policySha256 },
                    { "verifiedAt", voice.verifiedAt },
                    { "reason", voice.reason }
                };
            }
        }

        private static bool IsVirtual(string model)
        {
            return String.Equals(model, VirtualModel, StringComparison.OrdinalIgnoreCase);
        }

        private static bool GetDefaultAuto()
        {
            lock (StateGate)
            {
                bool preference;
                if (TryLoadDefaultAutoPreference(out preference)) State.defaultAuto = preference;
                return State.defaultAuto;
            }
        }

        private static void SetDefaultAuto(bool value)
        {
            lock (StateGate)
            {
                WriteDefaultAutoPreferenceLocked(value);
                State.defaultAuto = value;
                SaveStateLocked();
            }
        }

        private static bool IsThreadAuto(string threadId)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return false;
            lock (StateGate)
            {
                return State.autoThreads.Contains(threadId, StringComparer.OrdinalIgnoreCase);
            }
        }

        private static bool IsSecretaryThread(string threadId)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return false;
            lock (StateGate)
            {
                return State.secretaryThreads.Contains(threadId, StringComparer.OrdinalIgnoreCase);
            }
        }

        private static bool IsSecretaryTrigger(string taskText)
        {
            return ContainsAny((taskText ?? String.Empty).ToLowerInvariant(), new[] { PolicyTrigger });
        }

        private static void SetSecretaryThread(string threadId, bool enabled)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return;
            lock (StateGate)
            {
                State.secretaryThreads.RemoveAll(delegate(string value) { return String.Equals(value, threadId, StringComparison.OrdinalIgnoreCase); });
                if (enabled) State.secretaryThreads.Add(threadId);
                SaveStateLocked();
            }
        }

        private static bool IsUltraPending(string threadId)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return false;
            lock (StateGate)
            {
                return State.ultraApprovalThreads.Contains(threadId, StringComparer.OrdinalIgnoreCase);
            }
        }

        private static void SetUltraPending(string threadId, bool pending)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return;
            lock (StateGate)
            {
                State.ultraApprovalThreads.RemoveAll(delegate(string value) { return String.Equals(value, threadId, StringComparison.OrdinalIgnoreCase); });
                if (pending) State.ultraApprovalThreads.Add(threadId);
                SaveStateLocked();
            }
        }

        private static void SetThreadAuto(string threadId, bool enabled, RouteData route)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return;
            lock (StateGate)
            {
                State.autoThreads.RemoveAll(delegate(string value) { return String.Equals(value, threadId, StringComparison.OrdinalIgnoreCase); });
                if (enabled)
                {
                    State.autoThreads.Add(threadId);
                    if (route != null) State.lastRoutes[threadId] = route;
                }
                else
                {
                    State.lastRoutes.Remove(threadId);
                    State.secretaryThreads.RemoveAll(delegate(string value) { return String.Equals(value, threadId, StringComparison.OrdinalIgnoreCase); });
                    State.ultraApprovalThreads.RemoveAll(delegate(string value) { return String.Equals(value, threadId, StringComparison.OrdinalIgnoreCase); });
                }
                SaveStateLocked();
            }
        }

        private static RouteData GetLastRoute(string threadId)
        {
            if (String.IsNullOrWhiteSpace(threadId)) return null;
            lock (StateGate)
            {
                RouteData route;
                return State.lastRoutes.TryGetValue(threadId, out route) ? route : null;
            }
        }

        private static StateData LoadState()
        {
            StateData state = null;
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "state.json");
                if (File.Exists(path)) state = Json.Deserialize<StateData>(File.ReadAllText(path, Encoding.UTF8));
            }
            catch (Exception)
            {
                state = null;
            }
            if (state == null) state = new StateData();
            if (state.autoThreads == null) state.autoThreads = new List<string>();
            if (state.secretaryThreads == null) state.secretaryThreads = new List<string>();
            if (state.ultraApprovalThreads == null) state.ultraApprovalThreads = new List<string>();
            if (state.lastRoutes == null) state.lastRoutes = new Dictionary<string, RouteData>(StringComparer.OrdinalIgnoreCase);
            if (state.voiceBootstrap == null) state.voiceBootstrap = new VoiceStateData();
            bool preference;
            if (TryLoadDefaultAutoPreference(out preference)) state.defaultAuto = preference;
            return state;
        }

        private static bool TryLoadDefaultAutoPreference(out bool enabled)
        {
            enabled = false;
            try
            {
                if (!File.Exists(DefaultAutoPreferencePath)) return false;
                DefaultAutoPreferenceData preference = Json.Deserialize<DefaultAutoPreferenceData>(File.ReadAllText(DefaultAutoPreferencePath, Encoding.UTF8));
                if (preference == null || preference.schemaVersion != DefaultAutoPreferenceSchemaVersion) return false;
                enabled = preference.enabled;
                return true;
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static void WriteDefaultAutoPreferenceLocked(bool enabled)
        {
            Directory.CreateDirectory(InstallRoot);
            DefaultAutoPreferenceData preference = new DefaultAutoPreferenceData
            {
                schemaVersion = DefaultAutoPreferenceSchemaVersion,
                enabled = enabled
            };
            string temporary = DefaultAutoPreferencePath + ".tmp-" + Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture);
            try
            {
                File.WriteAllText(temporary, Json.Serialize(preference), new UTF8Encoding(false));
                if (File.Exists(DefaultAutoPreferencePath))
                {
                    File.Replace(temporary, DefaultAutoPreferencePath, null);
                }
                else
                {
                    File.Move(temporary, DefaultAutoPreferencePath);
                }
            }
            finally
            {
                if (File.Exists(temporary)) File.Delete(temporary);
            }
        }

        private static void SaveStateLocked()
        {
            Directory.CreateDirectory(InstallRoot);
            bool preference;
            if (TryLoadDefaultAutoPreference(out preference)) State.defaultAuto = preference;
            string temporary = StatePath + ".tmp-" + Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture);
            File.WriteAllText(temporary, Json.Serialize(State), new UTF8Encoding(false));
            if (File.Exists(StatePath))
            {
                File.Replace(temporary, StatePath, null);
            }
            else
            {
                File.Move(temporary, StatePath);
            }
        }

        private static int RunSelfTest()
        {
            SeedSelfTestCatalog();
            Dictionary<string, object> report = new Dictionary<string, object>();
            report["virtualModel"] = VirtualModel;
            report["storesPrompts"] = false;
            report["fast"] = ChooseRoute("สรุปไฟล์นี้แบบสั้น");
            report["balanced"] = ChooseRoute("เพิ่มหน้าตั้งค่าให้โปรเจกต์นี้");
            report["deep"] = ChooseRoute("วิเคราะห์ architecture และ root cause");
            report["critical"] = ChooseRoute("ตรวจ security และ database migration ก่อน production deploy");
            report["ultraApproval"] = ChooseRoute("ตรวจทั้งโค้ดเบสด้วยหลายเอเจนต์", false);
            report["ultraApproved"] = ChooseRoute("อนุมัติ", true, true);
            RouteData phaseStart = ChooseRoute("เพิ่มหน้าตั้งค่าให้โปรเจกต์นี้");
            report["phaseKeepsModel"] = ChooseAdaptiveRoute(phaseStart, "สรุปสถานะสั้น ๆ", false);
            report["phaseUpgrade"] = ChooseAdaptiveRoute(phaseStart, "วิเคราะห์ architecture และ root cause", false);
            report["phaseCriticalUpgrade"] = ChooseAdaptiveRoute(report["phaseUpgrade"] as RouteData, "ตรวจ security ก่อน deploy", false);
            report["phaseReset"] = ChooseAdaptiveRoute(report["phaseCriticalUpgrade"] as RouteData, "เริ่มงานใหม่: แปลข้อความนี้", false);
            PolicyData policy;
            string policyHash;
            string policyReason;
            bool policyVerified = TryLoadPolicy(out policy, out policyHash, out policyReason);
            if (policyVerified)
            {
                report["policyVersion"] = policy.policy_version;
                report["policySha256"] = policyHash;
            }
            else
            {
                report["policyVersion"] = null;
                report["policySha256"] = null;
            }
            Dictionary<string, object> voiceStatus = GetVoiceStatus();
            report["voiceBootstrap"] = voiceStatus;
            bool ready = policyVerified && IsVerifiedVoiceStatus(voiceStatus);
            report["status"] = ready ? "passed" : "degraded";
            Console.WriteLine(Json.Serialize(report));
            return ready ? 0 : 4;
        }

        private static void SeedSelfTestCatalog()
        {
            lock (CatalogGate)
            {
                AvailableModels.Clear();
                AvailableEfforts.Clear();
                foreach (string model in new[] { "gpt-6-astra", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol" })
                {
                    AvailableModels.Add(model);
                    AvailableEfforts[model] = new HashSet<string>(new[] { "low", "medium", "high", "xhigh", "ultra" }, StringComparer.OrdinalIgnoreCase);
                }
                CatalogDefaultModel = "gpt-5.6-luna";
            }
        }

        private static int WriteStatus()
        {
            Dictionary<string, object> report = new Dictionary<string, object>();
            report["virtualModel"] = VirtualModel;
            report["displayName"] = VirtualDisplayName;
            report["defaultAuto"] = GetDefaultAuto();
            lock (StateGate)
            {
                report["autoThreadCount"] = State.autoThreads.Count;
                report["secretaryThreadCount"] = State.secretaryThreads.Count;
                report["ultraApprovalThreadCount"] = State.ultraApprovalThreads.Count;
            }
            report["realCodexPresent"] = File.Exists(RealCodexPath);
            report["autoUpdateEnabled"] = File.Exists(RuntimeSyncScriptPath);
            report["runtimeSync"] = LoadRuntimeSyncStatus();
            report["storesPrompts"] = false;
            PolicyData policy;
            string policyHash;
            string policyReason;
            bool policyVerified = TryLoadPolicy(out policy, out policyHash, out policyReason);
            if (policyVerified)
            {
                report["policyVersion"] = policy.policy_version;
                report["policySha256"] = policyHash;
            }
            else
            {
                report["policyVersion"] = null;
                report["policySha256"] = null;
            }
            Dictionary<string, object> voiceStatus = GetVoiceStatus();
            report["voiceBootstrap"] = voiceStatus;
            bool realCodexPresent = File.Exists(RealCodexPath);
            bool ready = realCodexPresent && policyVerified && IsVerifiedVoiceStatus(voiceStatus);
            report["policyStatus"] = policyVerified ? "verified" : "unverified";
            report["status"] = ready ? "ready" : "degraded";
            Console.WriteLine(Json.Serialize(report));
            return ready ? 0 : (realCodexPresent ? 4 : 2);
        }

        private static bool IsVerifiedVoiceStatus(Dictionary<string, object> status)
        {
            string value = GetString(status, "status");
            return String.Equals(value, "configured", StringComparison.OrdinalIgnoreCase) ||
                String.Equals(value, "enforced", StringComparison.OrdinalIgnoreCase);
        }

        private static Dictionary<string, object> LoadRuntimeSyncStatus()
        {
            try
            {
                if (!File.Exists(RuntimeSyncStatePath)) return null;
                return Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(RuntimeSyncStatePath, Encoding.UTF8));
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static Dictionary<string, object> ParseObject(string json)
        {
            try { return Json.DeserializeObject(json) as Dictionary<string, object>; }
            catch (ArgumentException) { return null; }
            catch (InvalidOperationException) { return null; }
        }

        private static Dictionary<string, object> GetObject(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) ? value as Dictionary<string, object> : null;
        }

        private static IList GetArray(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) ? value as IList : null;
        }

        private static string GetString(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) && value != null
                ? Convert.ToString(value, CultureInfo.InvariantCulture)
                : null;
        }

        private static string IdKey(object value)
        {
            return value == null ? "null" : value.GetType().FullName + ":" + Convert.ToString(value, CultureInfo.InvariantCulture);
        }

        private static string JoinArguments(IEnumerable<string> args)
        {
            return String.Join(" ", args.Select(QuoteArgument).ToArray());
        }

        private static string QuoteArgument(string argument)
        {
            if (argument == null) return "\"\"";
            if (argument.Length > 0 && argument.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '\"' }) < 0) return argument;
            StringBuilder quoted = new StringBuilder();
            quoted.Append('\"');
            int backslashes = 0;
            foreach (char character in argument)
            {
                if (character == '\\')
                {
                    backslashes++;
                }
                else if (character == '\"')
                {
                    quoted.Append('\\', backslashes * 2 + 1);
                    quoted.Append('\"');
                    backslashes = 0;
                }
                else
                {
                    quoted.Append('\\', backslashes);
                    quoted.Append(character);
                    backslashes = 0;
                }
            }
            quoted.Append('\\', backslashes * 2);
            quoted.Append('\"');
            return quoted.ToString();
        }
    }
}
