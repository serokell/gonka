package main

import (
    "context"
    gonkaopenai "github.com/libermans/gonka-openai/go"
)

func main() {
    // Private key and SourceUrl can be provided directly or through environment variables
    // GONKA_PRIVATE_KEY and GONKA_SOURCE_URL respectively
    client, err := gonkaopenai.NewGonkaOpenAI(gonkaopenai.Options{
        GonkaPrivateKey: "0x1234...", // ECDSA private key for signing requests
        SourceUrl: "https://api.gonka.testnet.example.com", // Resolve endpoints from this SourceUrl
    })
    if err != nil {
        panic(err)
    }

    resp, err := client.Chat.Completions.New(context.Background(), openai.ChatCompletionNewParams{
        Model: "Qwen/QwQ-32B",
        Messages: []openai.ChatCompletionMessageParamUnion{
            openai.UserMessage("Hello!"),
        },
    })
    if err != nil {
        panic(err)
    }

    println(chatCompletion.Choices[0].Message.Content)
}
