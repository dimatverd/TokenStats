import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @State private var showAddProvider = false

    var body: some View {
        List {
            Section("Providers") {
                Button {
                    showAddProvider = true
                } label: {
                    Label("Add Provider", systemImage: "plus.circle")
                }
            }

            Section("Account") {
                Button(role: .destructive) {
                    authVM.logout()
                } label: {
                    Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
                }
            }

            Section("About") {
                HStack {
                    Text("Version")
                    Spacer()
                    Text("0.1.0")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Settings")
        .sheet(isPresented: $showAddProvider) {
            AddProviderView()
        }
    }
}

struct AddProviderView: View {
    @Environment(\.dismiss) var dismiss
    @State private var selectedProvider = "anthropic"
    @State private var apiKey = ""
    @State private var tier = "tier1"
    @State private var label = ""
    @State private var isLoading = false
    @State private var error: String?

    private let providers = [
        ("anthropic", "Anthropic (Claude)"),
        ("openai", "OpenAI"),
        ("google", "Google Vertex AI"),
    ]

    private let tiers = ["tier1", "tier2", "tier3", "tier4", "build", "scale"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Provider") {
                    Picker("Provider", selection: $selectedProvider) {
                        ForEach(providers, id: \.0) { id, name in
                            Text(name).tag(id)
                        }
                    }
                }

                Section("API Key") {
                    SecureField("Read-only API key", text: $apiKey)
                        .textContentType(.password)
                        .autocorrectionDisabled()

                    instructions
                }

                if selectedProvider == "anthropic" {
                    Section("Tier") {
                        Picker("Tier", selection: $tier) {
                            ForEach(tiers, id: \.self) { t in
                                Text(t).tag(t)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                }

                Section {
                    TextField("Label (optional)", text: $label)
                }

                if let error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
            }
            .navigationTitle("Add Provider")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        Task { await addProvider() }
                    }
                    .disabled(apiKey.isEmpty || isLoading)
                }
            }
        }
    }

    private var instructions: some View {
        Group {
            switch selectedProvider {
            case "anthropic":
                Text("Console -> Admin API Keys -> Create -> select only Read scopes")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case "openai":
                Text("Settings -> API Keys -> Create -> select Read permissions")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case "google":
                Text("GCP Console -> IAM -> Service Accounts -> Create -> add Viewer roles -> download JSON")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            default:
                EmptyView()
            }
        }
    }

    private func addProvider() async {
        isLoading = true
        error = nil
        do {
            try await APIClient.shared.addProvider(
                provider: selectedProvider,
                apiKey: apiKey,
                tier: selectedProvider == "anthropic" ? tier : nil,
                label: label.isEmpty ? nil : label
            )
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
