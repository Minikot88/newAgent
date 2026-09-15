using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace Kimmizo.CodexAuto
{
    public static class AutoModelScopeHarness
    {
        private const string VirtualModel = "kimmizo-auto";
        private const string VoiceBlockedMessage = "ยังตรวจสอบ voice bootstrap ของเลขาคิมไม่สำเร็จ จึงไม่เริ่มงานสาระสำคัญค่ะ";
        private const string CapsuleSchema = "kimmizo-capsule-v2";
        private const string CapsuleProjectId = "123e4567-e89b-12d3-a456-426614174000";
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        private static readonly BindingFlags PrivateStatic = BindingFlags.NonPublic | BindingFlags.Static;

        public static int Main(string[] args)
        {
            try
            {
                return Run(args);
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.ToString());
                return 1;
            }
        }

        private static int Run(string[] args)
        {
            if (args == null || args.Length < 2) throw new ArgumentException("project root and policy path are required");
            string projectRoot = Path.GetFullPath(args[0]);
            string policySource = Path.GetFullPath(args[1]);
            string installRoot = AppDomain.CurrentDomain.BaseDirectory;
            string policyPath = Path.Combine(installRoot, "model-policy.json");
            string policyHashPath = Path.Combine(installRoot, "model-policy.sha256");
            string globalSidecarPath = Path.Combine(installRoot, "voice-bootstrap.json");
            string statePath = Path.Combine(installRoot, "state.json");
            string defaultAutoPreferencePath = Path.Combine(installRoot, "default-auto.json");
            string projectMetaPath = Path.Combine(projectRoot, ".kimmizo", "core", "manifest.json");
            string projectSidecarPath = Path.Combine(projectRoot, ".kimmizo", "voice-bootstrap.json");

            File.Copy(policySource, policyPath, true);
            string policyHash = ComputeSha256(File.ReadAllBytes(policyPath));
            File.WriteAllText(policyHashPath, policyHash, new UTF8Encoding(false));
            WriteSidecar(globalSidecarPath, policyHash, null, null, null, null);
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            File.WriteAllText(statePath, "{\"defaultAuto\":false}", new UTF8Encoding(false));
            File.WriteAllText(defaultAutoPreferencePath, "{\"schemaVersion\":1,\"enabled\":true}", new UTF8Encoding(false));
            Environment.SetEnvironmentVariable("KIMMIZO_PROJECT_ROOT", projectRoot);

            SeedCatalog();
            MethodInfo getDefaultAuto = typeof(Program).GetMethod("GetDefaultAuto", PrivateStatic);
            MethodInfo setDefaultAuto = typeof(Program).GetMethod("SetDefaultAuto", PrivateStatic);
            Assert(getDefaultAuto != null && setDefaultAuto != null, "default Auto preference methods were not found");
            Assert(Convert.ToBoolean(getDefaultAuto.Invoke(null, new object[0])), "persisted default Auto preference did not override stale state");
            setDefaultAuto.Invoke(null, new object[] { false });
            Dictionary<string, object> disabledPreference = Deserialize(File.ReadAllText(defaultAutoPreferencePath, Encoding.UTF8));
            Assert(disabledPreference != null && !Convert.ToBoolean(disabledPreference["enabled"]), "default Auto off preference was not persisted");
            setDefaultAuto.Invoke(null, new object[] { true });
            Dictionary<string, object> enabledPreference = Deserialize(File.ReadAllText(defaultAutoPreferencePath, Encoding.UTF8));
            Assert(enabledPreference != null && Convert.ToBoolean(enabledPreference["enabled"]), "default Auto on preference was not persisted");
            MethodInfo transform = typeof(Program).GetMethod("TransformClientLine", PrivateStatic);
            if (transform == null) throw new InvalidOperationException("TransformClientLine was not found");
            MethodInfo serverTransform = typeof(Program).GetMethod("TransformServerLine", PrivateStatic);
            if (serverTransform == null) throw new InvalidOperationException("TransformServerLine was not found");

            TransformResultData limitFast = InvokeTurn(transform, "limit-fast", VirtualModel, "สรุปไฟล์นี้แบบสั้น", null);
            Dictionary<string, object> limitFastParams = GetObject(Deserialize(limitFast.Forward), "params");
            Assert(GetString(limitFastParams, "model") == "gpt-5.6-luna" && GetString(limitFastParams, "effort") == "low", "routine work did not use Luna/low");
            TransformResultData limitBalanced = InvokeTurn(transform, "limit-balanced", VirtualModel, "เพิ่มหน้าตั้งค่าให้โปรเจกต์นี้", null);
            Dictionary<string, object> limitBalancedParams = GetObject(Deserialize(limitBalanced.Forward), "params");
            Assert(GetString(limitBalancedParams, "model") == "gpt-5.6-luna" && GetString(limitBalancedParams, "effort") == "medium", "general coding did not use Luna/medium");
            TransformResultData limitDeep = InvokeTurn(transform, "limit-deep", VirtualModel, "วิเคราะห์ architecture และ root cause", null);
            Dictionary<string, object> limitDeepParams = GetObject(Deserialize(limitDeep.Forward), "params");
            Assert(GetString(limitDeepParams, "model") == "gpt-5.6-terra" && GetString(limitDeepParams, "effort") == "high", "complex work did not use Terra/high");
            TransformResultData limitCritical = InvokeTurn(transform, "limit-critical", VirtualModel, "ตรวจ security ก่อน production deploy", null);
            Dictionary<string, object> limitCriticalParams = GetObject(Deserialize(limitCritical.Forward), "params");
            Assert(GetString(limitCriticalParams, "model") == "gpt-5.6-sol" && GetString(limitCriticalParams, "effort") == "high", "high-stakes work did not use Sol/high");
            Assert(GetString(limitFastParams, "model") != "gpt-6-astra" && GetString(limitBalancedParams, "model") != "gpt-6-astra" && GetString(limitDeepParams, "model") != "gpt-6-astra" && GetString(limitCriticalParams, "model") != "gpt-6-astra", "Auto selected manual-only Astra");

            SeedAstraOnlyCatalog();
            Environment.SetEnvironmentVariable("KIMMIZO_AUTO_FALLBACK", "gpt-6-astra");
            TransformResultData astraFallback = InvokeTurn(transform, "astra-fallback", VirtualModel, "สรุปสถานะ", null);
            Environment.SetEnvironmentVariable("KIMMIZO_AUTO_FALLBACK", null);
            Assert(IsBlocked(astraFallback, -32072), "manual-only Astra was accepted through the Auto fallback");
            SeedCatalog();

            TransformResultData explicitStart = InvokeThreadStart(transform, "explicit-start", "gpt-5.6-terra");
            Dictionary<string, object> explicitMessage = Deserialize(explicitStart.Forward);
            Dictionary<string, object> explicitParams = GetObject(explicitMessage, "params");
            Assert(explicitStart.Response == null && explicitParams != null && GetString(explicitParams, "model") == "gpt-5.6-terra", "explicit concrete thread/start was routed through Auto");

            TransformResultData autoStart = InvokeThreadStart(transform, "auto-start", null);
            Assert(autoStart.Response == null && autoStart.Forward != null, "default Auto thread/start was not forwarded");
            TransformResultData interleavedManualStart = InvokeThreadStart(transform, "interleaved-manual", "gpt-5.6-terra");
            Assert(interleavedManualStart.Response == null, "interleaved manual thread/start was blocked");
            string manualStartedNotification = InvokeServer(serverTransform, Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "method", "thread/started" },
                { "params", new Dictionary<string, object> { { "thread", new Dictionary<string, object> { { "id", "manual-thread" }, { "model", "gpt-5.6-terra" } } } } }
            }));
            Dictionary<string, object> manualStartedMessage = Deserialize(manualStartedNotification);
            Assert(GetString(GetObject(GetObject(manualStartedMessage, "params"), "thread"), "model") == "gpt-5.6-terra", "unbound thread/started notification cross-marked a manual thread");
            InvokeServer(serverTransform, Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", "interleaved-manual" },
                { "result", new Dictionary<string, object> { { "thread", new Dictionary<string, object> { { "id", "manual-thread" }, { "model", "gpt-5.6-terra" } } } } }
            }));
            string autoStartedResponse = InvokeServer(serverTransform, Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", "auto-start" },
                { "result", new Dictionary<string, object> { { "thread", new Dictionary<string, object> { { "id", "auto-thread" }, { "model", "gpt-5.6-terra" } } } } }
            }));
            Assert(GetString(GetObject(GetObject(Deserialize(autoStartedResponse), "result"), "thread"), "model") == VirtualModel, "Auto thread/start response was not bound to its request ID");
            string manualStartedAfterAuto = InvokeServer(serverTransform, Json.Serialize(new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "method", "thread/started" },
                { "params", new Dictionary<string, object> { { "thread", new Dictionary<string, object> { { "id", "manual-thread" }, { "model", "gpt-5.6-terra" } } } } }
            }));
            Assert(GetString(GetObject(GetObject(Deserialize(manualStartedAfterAuto), "params"), "thread"), "model") == "gpt-5.6-terra", "manual thread was cross-marked after an Auto response");

            ClearCatalog();
            TransformResultData unobservedStart = InvokeThreadStart(transform, "unobserved-start", VirtualModel);
            Assert(IsBlocked(unobservedStart, -32072), "Auto selected a model that was not observed in the catalog");
            SeedUnrelatedCatalog();
            TransformResultData unrelatedCatalogStart = InvokeThreadStart(transform, "unrelated-catalog-start", VirtualModel);
            Assert(IsBlocked(unrelatedCatalogStart, -32072), "Auto selected a model absent from an unrelated-only catalog");
            SeedCatalog();

            TransformResultData unrelated = InvokeTurn(transform, "unrelated", VirtualModel, "สรุปสถานะ", null);
            Assert(unrelated.Response == null, "unrelated Auto turn was blocked");
            Assert(!HasVoiceContext(unrelated.Forward), "unrelated Auto turn received voice context");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData first = InvokeTurn(transform, "secretary", VirtualModel, "เลขาคิม ช่วยสรุปสถานะ", null);
            Assert(first.Response == null && HasVoiceContext(first.Forward), "first trigger did not inject voice context");
            TransformResultData continuity = InvokeTurn(transform, "secretary", null, "ช่วยสรุปสถานะต่อ", null);
            Assert(continuity.Response == null && HasVoiceContext(continuity.Forward), "secretary continuity did not inject voice context");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, "other-trigger", null, null, null);
            TransformResultData precedence = InvokeTurn(transform, "precedence", VirtualModel, "เลขาคิม งานสำคัญ", null);
            Assert(IsBlocked(precedence), "invalid project sidecar fell back to global sidecar");

            WriteSchemaZeroSidecar(projectSidecarPath, policyHash);
            WriteProjectManifest(projectMetaPath, CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(projectSidecarPath))));
            TransformResultData invalidSchema = InvokeTurn(transform, "invalid-schema", VirtualModel, "เลขาคิม งานสำคัญ", null);
            Assert(IsBlocked(invalidSchema), "schema-zero sidecar was silently accepted");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            Dictionary<string, object> invalidCapsuleSchema = CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(projectSidecarPath)));
            invalidCapsuleSchema["schema"] = "kimmizo-capsule-v1";
            WriteProjectManifest(projectMetaPath, invalidCapsuleSchema);
            AssertVoiceBlocked(InvokeTurn(transform, "invalid-capsule-schema", VirtualModel, "เลขาคิม งานสำคัญ", null), "invalid capsule schema was trusted");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            Dictionary<string, object> unknownCapsuleMajor = CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(projectSidecarPath)));
            unknownCapsuleMajor["schema_version"] = 99;
            WriteProjectManifest(projectMetaPath, unknownCapsuleMajor);
            AssertVoiceBlocked(InvokeTurn(transform, "unknown-capsule-major", VirtualModel, "เลขาคิม งานสำคัญ", null), "unknown capsule major was trusted");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            Dictionary<string, object> inactiveCapsule = CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(projectSidecarPath)));
            inactiveCapsule["lifecycle"] = "inactive";
            WriteProjectManifest(projectMetaPath, inactiveCapsule);
            AssertVoiceBlocked(InvokeTurn(transform, "inactive-capsule", VirtualModel, "เลขาคิม งานสำคัญ", null), "inactive capsule was trusted");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            Dictionary<string, object> incompleteCapsule = CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(projectSidecarPath)));
            incompleteCapsule["project_id"] = null;
            WriteProjectManifest(projectMetaPath, incompleteCapsule);
            AssertVoiceBlocked(InvokeTurn(transform, "incomplete-capsule", VirtualModel, "เลขาคิม งานสำคัญ", null), "incomplete capsule was trusted");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            File.AppendAllText(projectSidecarPath, "\n", new UTF8Encoding(false));
            AssertVoiceBlocked(InvokeTurn(transform, "bootstrap-hash-mismatch", VirtualModel, "เลขาคิม งานสำคัญ", null), "bootstrap bytes were not bound to the capsule manifest");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            TransformResultData notificationBlocked = InvokeTurnWithoutId(transform, "notification", VirtualModel, "เลขาคิม ทำงานสำคัญ", null);
            Assert(notificationBlocked.Forward == null && notificationBlocked.Response == null, "blocked notification produced a response or was forwarded");
            TransformResultData blocked = InvokeTurn(transform, "blocked", VirtualModel, "เลขาคิม ทำงานสำคัญ", null);
            Assert(IsBlocked(blocked), "invalid first trigger was forwarded");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData unmarked = InvokeTurn(transform, "blocked", null, "ช่วยสรุปสถานะ", null);
            Assert(unmarked.Response == null && !HasVoiceContext(unmarked.Forward), "blocked first trigger marked the thread secretary");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            TransformResultData manual = InvokeTurn(transform, "manual", "gpt-5.6-terra", "ทำงานสำคัญ", null);
            Assert(manual.Response == null && !HasVoiceContext(manual.Forward), "manual-model thread was voice-gated");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData scalarUltra = InvokeTurnRaw(transform, "scalar-ultra", VirtualModel, "whole codebase", "unsafe");
            Assert(IsBlocked(scalarUltra, -32073), "Ultra scalar additionalContext was clobbered");
            TransformResultData listUltra = InvokeTurnRaw(transform, "list-ultra", VirtualModel, "whole codebase", new ArrayList { "unsafe" });
            Assert(IsBlocked(listUltra, -32073), "Ultra list additionalContext was clobbered");

            string[] denialPhrases = new[]
            {
                "do not approve Ultra",
                "don't approve ultra",
                "not approve ultra",
                "deny ultra",
                "decline ultra",
                "ไม่อนุมัติ"
            };
            for (int index = 0; index < denialPhrases.Length; index++)
            {
                string denialThread = "denial-" + index.ToString();
                TransformResultData pendingUltra = InvokeTurn(transform, denialThread, VirtualModel, "เลขาคิม ตรวจ whole codebase", null);
                Dictionary<string, object> pendingMessage = Deserialize(pendingUltra.Forward);
                Dictionary<string, object> pendingContext = GetObject(GetObject(pendingMessage, "params"), "additionalContext");
                Assert(pendingContext != null && pendingContext.ContainsKey("kimmizo_auto_ultra_approval"), "denial setup did not create Ultra pending state");
                TransformResultData denial = InvokeTurn(transform, denialThread, null, denialPhrases[index], null);
                AssertNonUltraDenial(denial, denialPhrases[index]);
            }
            TransformResultData pendingApproval = InvokeTurn(transform, "approval", VirtualModel, "เลขาคิม ตรวจ whole codebase", null);
            Assert(pendingApproval.Response == null, "approval setup failed");
            TransformResultData approval = InvokeTurn(transform, "approval", null, "อนุมัติ", null);
            Dictionary<string, object> approvalMessage = Deserialize(approval.Forward);
            Dictionary<string, object> approvalParams = GetObject(approvalMessage, "params");
            Assert(approval.Response == null && GetString(approvalParams, "effort") == "ultra", "explicit approval no longer authorizes Ultra while pending");

            TransformResultData mixedEnglishSetup = InvokeTurn(transform, "mixed-english", VirtualModel, "เลขาคิม ตรวจ whole codebase", null);
            Assert(mixedEnglishSetup.Response == null && HasVoiceContext(mixedEnglishSetup.Forward), "mixed English setup did not mark a secretary thread");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            AssertVoiceBlocked(InvokeTurn(transform, "mixed-english", null, "approve Ultra and deploy now", null), "mixed English approval and work bypassed the voice gate");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData mixedThaiSetup = InvokeTurn(transform, "mixed-thai", VirtualModel, "เลขาคิม ตรวจ whole codebase", null);
            Assert(mixedThaiSetup.Response == null && HasVoiceContext(mixedThaiSetup.Forward), "mixed Thai setup did not mark a secretary thread");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            AssertVoiceBlocked(InvokeTurn(transform, "mixed-thai", null, "อนุมัติ ultra แล้ว deploy ตอนนี้", null), "mixed Thai approval and work bypassed the voice gate");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData approvalOnlySetup = InvokeTurn(transform, "approval-only-invalid-bootstrap", VirtualModel, "เลขาคิม ตรวจ whole codebase", null);
            Assert(approvalOnlySetup.Response == null, "approval-only setup failed");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            TransformResultData approvalOnly = InvokeTurn(transform, "approval-only-invalid-bootstrap", null, "อนุมัติ", null);
            Dictionary<string, object> approvalOnlyMessage = Deserialize(approvalOnly.Forward);
            Dictionary<string, object> approvalOnlyParams = GetObject(approvalOnlyMessage, "params");
            Assert(approvalOnly.Response == null && GetString(approvalOnlyParams, "effort") == "ultra", "approval-only Ultra re-arm was blocked by the voice gate");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);

            Dictionary<string, object> existingContext = new Dictionary<string, object>();
            existingContext["existing"] = new Dictionary<string, object> { { "kind", "application" }, { "value", "keep" } };
            TransformResultData ultra = InvokeTurn(transform, "ultra", VirtualModel, "เลขาคิม ตรวจ whole codebase", existingContext);
            Dictionary<string, object> ultraMessage = Deserialize(ultra.Forward);
            Dictionary<string, object> ultraParams = GetObject(ultraMessage, "params");
            Dictionary<string, object> ultraContext = GetObject(ultraParams, "additionalContext");
            Assert(ultra.Response == null && ultraContext.ContainsKey("kimmizo_voice_bootstrap"), "Ultra trigger missed voice context");
            Assert(ultraContext.ContainsKey("kimmizo_auto_ultra_approval"), "Ultra context was clobbered by voice context");
            Assert(ultraContext.ContainsKey("existing"), "existing additional context was clobbered");

            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);
            TransformResultData disableStart = InvokeTurn(transform, "disable", VirtualModel, "เลขาคิม ช่วยสรุป", null);
            Assert(HasVoiceContext(disableStart.Forward), "disable setup did not mark secretary thread");
            InvokeSettings(transform, "disable", "gpt-5.6-terra");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, "0000000000000000000000000000000000000000000000000000000000000000", null, null, null, null);
            TransformResultData disabled = InvokeTurn(transform, "disable", null, "ช่วยสรุปต่อ", null);
            Assert(disabled.Response == null && !HasVoiceContext(disabled.Forward), "disabled thread retained secretary state");

            File.Delete(projectSidecarPath);
            DiagnosticResult selfTest = InvokeDiagnostic(typeof(Program).GetMethod("RunSelfTest", PrivateStatic));
            Dictionary<string, object> selfTestReport = Deserialize(selfTest.Output);
            Assert(selfTest.Code != 0 && GetString(selfTestReport, "status") == "degraded", "self-test claimed readiness without voice bootstrap");
            DiagnosticResult status = InvokeDiagnostic(typeof(Program).GetMethod("WriteStatus", PrivateStatic));
            Dictionary<string, object> statusReport = Deserialize(status.Output);
            Assert(status.Code != 0 && GetString(statusReport, "status") == "degraded", "status claimed readiness without voice bootstrap");
            WriteVerifiedProjectSidecar(projectSidecarPath, projectMetaPath, policyHash, null, null, null, null);

            string stateText = File.Exists(statePath) ? File.ReadAllText(statePath, Encoding.UTF8) : String.Empty;
            Assert(stateText.IndexOf("secretaryThreads", StringComparison.Ordinal) >= 0, "secretary thread state was not persisted");
            Dictionary<string, object> state = Deserialize(stateText);
            IList secretaryThreads = state == null ? null : GetArray(state, "secretaryThreads");
            Assert(secretaryThreads != null && ContainsString(secretaryThreads, "secretary") && ContainsString(secretaryThreads, "ultra"), "secretary thread IDs were not persisted");
            Assert(stateText.IndexOf("เลขาคิม ช่วยสรุปสถานะ", StringComparison.Ordinal) < 0, "prompt text was persisted");
            Assert(stateText.IndexOf("whole codebase", StringComparison.Ordinal) < 0, "task text was persisted");
            Console.WriteLine("AUTO_SCOPE_HARNESS_PASS");
            return 0;
        }

        private static void SeedCatalog()
        {
            MethodInfo addAutoModel = typeof(Program).GetMethod("AddAutoModel", PrivateStatic);
            ArrayList models = new ArrayList();
            foreach (string model in new[] { "gpt-6-astra", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol" })
            {
                models.Add(new Dictionary<string, object>
                {
                    { "model", model },
                    { "isDefault", model == "gpt-5.6-sol" },
                    { "supportedReasoningEfforts", new ArrayList
                        {
                            new Dictionary<string, object> { { "reasoningEffort", "low" } },
                            new Dictionary<string, object> { { "reasoningEffort", "medium" } },
                            new Dictionary<string, object> { { "reasoningEffort", "high" } },
                            new Dictionary<string, object> { { "reasoningEffort", "xhigh" } },
                            new Dictionary<string, object> { { "reasoningEffort", "ultra" } }
                        }
                    }
                });
            }
            Dictionary<string, object> result = new Dictionary<string, object>
            {
                { "data", models }
            };
            object changed = addAutoModel.Invoke(null, new object[] { result });
            Assert(Convert.ToBoolean(changed), "test catalog could not be seeded");
        }

        private static void ClearCatalog()
        {
            MethodInfo addAutoModel = typeof(Program).GetMethod("AddAutoModel", PrivateStatic);
            Dictionary<string, object> result = new Dictionary<string, object>
            {
                { "data", new ArrayList() }
            };
            addAutoModel.Invoke(null, new object[] { result });
        }

        private static void SeedAstraOnlyCatalog()
        {
            MethodInfo addAutoModel = typeof(Program).GetMethod("AddAutoModel", PrivateStatic);
            Dictionary<string, object> model = new Dictionary<string, object>
            {
                { "model", "gpt-6-astra" },
                { "isDefault", true },
                { "supportedReasoningEfforts", new ArrayList
                    {
                        new Dictionary<string, object> { { "reasoningEffort", "low" } },
                        new Dictionary<string, object> { { "reasoningEffort", "medium" } },
                        new Dictionary<string, object> { { "reasoningEffort", "high" } },
                        new Dictionary<string, object> { { "reasoningEffort", "xhigh" } },
                        new Dictionary<string, object> { { "reasoningEffort", "max" } },
                        new Dictionary<string, object> { { "reasoningEffort", "ultra" } }
                    }
                }
            };
            Dictionary<string, object> result = new Dictionary<string, object>
            {
                { "data", new ArrayList { model } }
            };
            object changed = addAutoModel.Invoke(null, new object[] { result });
            Assert(Convert.ToBoolean(changed), "Astra-only test catalog could not be seeded");
        }

        private static void SeedUnrelatedCatalog()
        {
            MethodInfo addAutoModel = typeof(Program).GetMethod("AddAutoModel", PrivateStatic);
            Dictionary<string, object> model = new Dictionary<string, object>
            {
                { "model", "gpt-4-unrelated" },
                { "isDefault", true },
                { "supportedReasoningEfforts", new ArrayList
                    {
                        new Dictionary<string, object> { { "reasoningEffort", "medium" } }
                    }
                }
            };
            Dictionary<string, object> result = new Dictionary<string, object>
            {
                { "data", new ArrayList { model } }
            };
            object changed = addAutoModel.Invoke(null, new object[] { result });
            Assert(Convert.ToBoolean(changed), "unrelated-only test catalog could not be seeded");
        }

        private static TransformResultData InvokeThreadStart(MethodInfo transform, string requestId, string model)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            if (model != null) parameters["model"] = model;
            Dictionary<string, object> message = new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", requestId },
                { "method", "thread/start" },
                { "params", parameters }
            };
            return Invoke(transform, Json.Serialize(message));
        }

        private static string InvokeServer(MethodInfo transform, string line)
        {
            return transform.Invoke(null, new object[] { line }) as string;
        }

        private static DiagnosticResult InvokeDiagnostic(MethodInfo diagnostic)
        {
            StringWriter capture = new StringWriter();
            TextWriter original = Console.Out;
            Console.SetOut(capture);
            try
            {
                return new DiagnosticResult
                {
                    Code = Convert.ToInt32(diagnostic.Invoke(null, new object[0])),
                    Output = capture.ToString().Trim()
                };
            }
            finally
            {
                Console.SetOut(original);
            }
        }

        private static TransformResultData InvokeTurn(MethodInfo transform, string threadId, string model, string text, Dictionary<string, object> context)
        {
            return InvokeTurnRaw(transform, threadId, model, text, context);
        }

        private static TransformResultData InvokeTurnRaw(MethodInfo transform, string threadId, string model, string text, object context)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            parameters["threadId"] = threadId;
            if (model != null) parameters["model"] = model;
            parameters["input"] = new ArrayList
            {
                new Dictionary<string, object> { { "type", "text" }, { "text", text } }
            };
            if (context != null) parameters["additionalContext"] = context;
            Dictionary<string, object> message = new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", threadId },
                { "method", "turn/start" },
                { "params", parameters }
            };
            return Invoke(transform, Json.Serialize(message));
        }

        private static TransformResultData InvokeTurnWithoutId(MethodInfo transform, string threadId, string model, string text, object context)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            parameters["threadId"] = threadId;
            if (model != null) parameters["model"] = model;
            parameters["input"] = new ArrayList
            {
                new Dictionary<string, object> { { "type", "text" }, { "text", text } }
            };
            if (context != null) parameters["additionalContext"] = context;
            Dictionary<string, object> message = new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "method", "turn/start" },
                { "params", parameters }
            };
            return Invoke(transform, Json.Serialize(message));
        }

        private static void InvokeSettings(MethodInfo transform, string threadId, string model)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>
            {
                { "threadId", threadId },
                { "model", model }
            };
            Dictionary<string, object> message = new Dictionary<string, object>
            {
                { "jsonrpc", "2.0" },
                { "id", "settings-" + threadId },
                { "method", "thread/settings/update" },
                { "params", parameters }
            };
            Invoke(transform, Json.Serialize(message));
        }

        private static TransformResultData Invoke(MethodInfo transform, string line)
        {
            object result = transform.Invoke(null, new object[] { line });
            Type resultType = result.GetType();
            return new TransformResultData
            {
                Forward = resultType.GetProperty("ForwardLine").GetValue(result, null) as string,
                Response = resultType.GetProperty("ImmediateResponse").GetValue(result, null) as string
            };
        }

        private static void WriteVerifiedProjectSidecar(string sidecarPath, string manifestPath, string policyHash, string trigger, string pronoun, string suffix, string instruction)
        {
            WriteSidecar(sidecarPath, policyHash, trigger, pronoun, suffix, instruction);
            WriteProjectManifest(manifestPath, CreateProjectManifest(policyHash, ComputeSha256(File.ReadAllBytes(sidecarPath))));
        }

        private static Dictionary<string, object> CreateProjectManifest(string policyHash, string bootstrapHash)
        {
            Dictionary<string, object> fileHashes = new Dictionary<string, object>
            {
                { ".kimmizo/voice-bootstrap.json", bootstrapHash }
            };
            string aggregateHash = ComputeSha256(Encoding.UTF8.GetBytes(".kimmizo/voice-bootstrap.json:" + bootstrapHash + "\n"));
            string agentsBlockHash = ComputeSha256(Encoding.UTF8.GetBytes("kimweaver-v2-managed-block"));
            string migrationHash = ComputeSha256(Encoding.UTF8.GetBytes("kimweaver-v2-migration"));
            string sourceRevision = ComputeSha256(Encoding.ASCII.GetBytes(aggregateHash + "\n" + agentsBlockHash + "\n" + policyHash + "\n"));
            return new Dictionary<string, object>
            {
                { "schema", CapsuleSchema },
                { "schema_version", 2 },
                { "project_id", CapsuleProjectId },
                { "capsule_version", "2.0.0" },
                { "core_version", "2.0.0" },
                { "adapter_version", "2.0.0" },
                { "source_revision", sourceRevision },
                { "source_provenance", new Dictionary<string, object>
                    {
                        { "kind", "vendored_project_local_snapshot" },
                        { "runtime", "stdlib_only" }
                    }
                },
                { "provenance", "vendored_project_local_snapshot" },
                { "file_hashes", fileHashes },
                { "aggregate_sha256", aggregateHash },
                { "bootstrap_sha256", bootstrapHash },
                { "bootstrap_hash", bootstrapHash },
                { "policy_sha256", policyHash },
                { "migration_sha256", migrationHash },
                { "agents_block_sha256", agentsBlockHash },
                { "active_revision", "v2-" + sourceRevision.Substring(0, 16) },
                { "previous_revision", null },
                { "compatibility", new Dictionary<string, object>
                    {
                        { "minimum_setup_version", "1.0.0" },
                        { "legacy_projection", "hash-only-v1" }
                    }
                },
                { "legacy_projection", "hash-only-v1" },
                { "lifecycle", "active" }
            };
        }

        private static void WriteProjectManifest(string path, Dictionary<string, object> manifest)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, Json.Serialize(manifest), new UTF8Encoding(false));
        }

        private static void WriteSidecar(string path, string policyHash, string trigger, string pronoun, string suffix, string instruction)
        {
            string directory = Path.GetDirectoryName(path);
            Directory.CreateDirectory(directory);
            Dictionary<string, object> sidecar = new Dictionary<string, object>
            {
                { "schemaVersion", 3 },
                { "policyVersion", "3.0.0" },
                { "policySha256", policyHash },
                { "trigger", trigger ?? "เลขาคิม" },
                { "pronoun", pronoun ?? "ฉัน" },
                { "suffix", suffix ?? "ค่ะ" },
                { "instruction", instruction ?? "เมื่อถูกเรียกว่า เลขาคิม ให้ตอบภาษาไทย ใช้สรรพนาม ฉัน และลงท้ายด้วย ค่ะ" },
                { "blockedMessage", "ยังตรวจสอบ voice bootstrap ของเลขาคิมไม่สำเร็จ จึงไม่เริ่มงานสาระสำคัญค่ะ" }
            };
            File.WriteAllText(path, Json.Serialize(sidecar), new UTF8Encoding(false));
        }

        private static void WriteSchemaZeroSidecar(string path, string policyHash)
        {
            Dictionary<string, object> sidecar = new Dictionary<string, object>
            {
                { "schemaVersion", 0 },
                { "policyVersion", "3.0.0" },
                { "policySha256", policyHash },
                { "trigger", "เลขาคิม" },
                { "pronoun", "ฉัน" },
                { "suffix", "ค่ะ" },
                { "instruction", "เมื่อเรียกว่า เลขาคิม ให้ตอบภาษาไทย ใช้สรรพนาม ฉัน และลงท้ายด้วย ค่ะ" },
                { "blockedMessage", "ยังตรวจสอบ voice bootstrap ของเลขาคิมไม่สำเร็จ จึงไม่เริ่มงานสาระสำคัญค่ะ" }
            };
            File.WriteAllText(path, Json.Serialize(sidecar), new UTF8Encoding(false));
        }

        private static bool IsBlocked(TransformResultData result)
        {
            return IsBlocked(result, -32071);
        }

        private static bool IsBlocked(TransformResultData result, int expectedCode)
        {
            if (result == null || result.Forward != null || String.IsNullOrWhiteSpace(result.Response)) return false;
            Dictionary<string, object> response = Deserialize(result.Response);
            Dictionary<string, object> error = GetObject(response, "error");
            object code;
            return error != null && error.TryGetValue("code", out code) && Convert.ToInt32(code) == expectedCode;
        }

        private static void AssertVoiceBlocked(TransformResultData result, string message)
        {
            Assert(IsBlocked(result), message);
            Dictionary<string, object> response = Deserialize(result.Response);
            Dictionary<string, object> error = GetObject(response, "error");
            Assert(GetString(error, "message") == VoiceBlockedMessage, "voice block did not return the fixed response: " + message);
            Assert(result.Forward == null && !HasVoiceContext(result.Forward), "voice block forwarded model, tool, or spawn context: " + message);
        }

        private static void AssertNonUltraDenial(TransformResultData result, string phrase)
        {
            Assert(result != null && result.Response == null && result.Forward != null, "denial was blocked or dropped: " + phrase);
            Dictionary<string, object> message = Deserialize(result.Forward);
            Dictionary<string, object> parameters = GetObject(message, "params");
            Dictionary<string, object> context = GetObject(parameters, "additionalContext");
            Assert(GetString(parameters, "effort") != "ultra", "denial selected ultra effort: " + phrase);
            Assert(context == null || !context.ContainsKey("kimmizo_auto_ultra_approval"), "denial re-added Ultra approval context: " + phrase);
        }

        private static bool HasVoiceContext(string line)
        {
            if (String.IsNullOrWhiteSpace(line)) return false;
            Dictionary<string, object> message = Deserialize(line);
            Dictionary<string, object> parameters = GetObject(message, "params");
            Dictionary<string, object> context = GetObject(parameters, "additionalContext");
            return context != null && context.ContainsKey("kimmizo_voice_bootstrap");
        }

        private static Dictionary<string, object> Deserialize(string line)
        {
            return Json.DeserializeObject(line) as Dictionary<string, object>;
        }

        private static Dictionary<string, object> GetObject(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) ? value as Dictionary<string, object> : null;
        }

        private static string GetString(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : null;
        }

        private static IList GetArray(Dictionary<string, object> source, string key)
        {
            if (source == null) return null;
            object value;
            return source.TryGetValue(key, out value) ? value as IList : null;
        }

        private static bool ContainsString(IList values, string expected)
        {
            foreach (object value in values)
            {
                if (String.Equals(Convert.ToString(value), expected, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        private static string ComputeSha256(byte[] bytes)
        {
            using (SHA256 sha256 = SHA256.Create())
            {
                byte[] digest = sha256.ComputeHash(bytes);
                StringBuilder result = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest) result.Append(value.ToString("x2"));
                return result.ToString();
            }
        }

        private static void Assert(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        private sealed class TransformResultData
        {
            public string Forward { get; set; }
            public string Response { get; set; }
        }

        private sealed class DiagnosticResult
        {
            public int Code { get; set; }
            public string Output { get; set; }
        }
    }
}
