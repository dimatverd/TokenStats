import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authVM: AuthViewModel
    @State private var email = ""
    @State private var password = ""
    @State private var isRegistering = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                VStack(spacing: 8) {
                    Image(systemName: "chart.bar.fill")
                        .font(.system(size: 48))
                        .foregroundStyle(.blue)
                    Text("TokenStats")
                        .font(.largeTitle.bold())
                    Text("Monitor your LLM usage")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 16) {
                    TextField("Email", text: $email)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)

                    SecureField("Password", text: $password)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(isRegistering ? .newPassword : .password)

                    if let error = authVM.error {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }

                    Button {
                        Task {
                            if isRegistering {
                                await authVM.register(email: email, password: password)
                            } else {
                                await authVM.login(email: email, password: password)
                            }
                        }
                    } label: {
                        if authVM.isLoading {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text(isRegistering ? "Create Account" : "Log In")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(email.isEmpty || password.count < 8 || authVM.isLoading)

                    Button(isRegistering ? "Already have an account? Log In" : "Don't have an account? Register") {
                        isRegistering.toggle()
                        authVM.error = nil
                    }
                    .font(.footnote)
                }
                .padding(.horizontal)

                Spacer()
                Spacer()
            }
            .navigationTitle("")
        }
    }
}
