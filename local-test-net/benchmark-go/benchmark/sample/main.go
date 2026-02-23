package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	//"fmt"
	"github.com/cosmos/cosmos-sdk/types/tx"
	gogoproto "github.com/cosmos/gogoproto/proto"
	protoV1 "github.com/golang/protobuf/proto"
	gonkaopenai "github.com/gonka-ai/gonka-openai/go"
	"github.com/gorilla/websocket"
	openai "github.com/openai/openai-go"
	inference "github.com/productscience/inference/api/inference/inference"
	"log"
	"os"
	"slices"
	"strconv"
	"time"
	//anypb "github.com/cosmos/gogoproto/types/any"
	//"google.golang.org/protobuf/encoding/protojson"
	//"google.golang.org/protobuf/proto"
	//gogotypes "github.com/cosmos/gogoproto/types"
)

const pongWait = 60 * time.Second

type InferenceIdReport struct {
	inference_id InferenceId
	start_msg_at int64
	end_msg_at   int64
}

type TxNotification struct {
	Result struct {
		Data struct {
			Value struct {
				TxResult struct {
					Tx string `json:"tx"`
				}
			} `json:"value"`
		} `json:"data"`
		Events struct {
			TxAction []string `json:"message.action"`
			TxHash   []string `json:"tx.hash"`
			TxHeight []string `json:"tx.height"`
		} `json:"events"`
	} `json:"result"`
}

type TxMessage struct {
	MessageType      string      `json:"@type"`
	InferenceId      InferenceId `json:"inference_id"`
	RequestTimestamp int64       `json:"request_timestamp"`
}

type TxDecoded struct {
	Body struct {
		Messages []TxMessage `json:"messages"`
	} `json:"body"`
}

type TxHash string
type InferenceId string

func decode_tx(tx string) (*TxDecoded, error) {
	var result_tx TxDecoded
	result_tx.Body.Messages = decodeTx_(tx)
	return &result_tx, nil
}

func decodeTx_(txBase64 string) []TxMessage {
	var messages []TxMessage
	txBytes, err := base64.StdEncoding.DecodeString(txBase64)
	if err != nil {
		panic(err)
	}

	var protoTx tx.Tx
	if err := protoV1.Unmarshal(txBytes, &protoTx); err != nil {
		panic(err)
	}

	if protoTx.Body == nil {
		return messages
	}

	for _, msgAny := range protoTx.Body.Messages {

		switch msgAny.TypeUrl {

		case "/inference.inference.MsgStartInference":
			var msg inference.MsgStartInference

			err := gogoproto.Unmarshal(msgAny.Value, &msg)
			if err != nil {
				panic(err)
			}
			messages = append(messages, TxMessage{MessageType: msgAny.TypeUrl, InferenceId: InferenceId(msg.InferenceId), RequestTimestamp: msg.RequestTimestamp})

		case "/inference.inference.MsgFinishInference":
			var msg inference.MsgFinishInference

			err := gogoproto.Unmarshal(msgAny.Value, &msg)
			if err != nil {
				panic(err)
			}
			messages = append(messages, TxMessage{MessageType: msgAny.TypeUrl, InferenceId: InferenceId(msg.InferenceId), RequestTimestamp: msg.RequestTimestamp})
		default:
			log.Printf("Unknown:%s", msgAny.TypeUrl)
		}

	}
	return messages
}

func handle_connection(conn *websocket.Conn, tx_hash_notification_chan chan<- TxDecoded) {
	defer conn.Close()

	var last_height int64

	done := make(chan struct{})
	defer close(done)

	// Start ping sender
	go func() {
		ticker := time.NewTicker((pongWait * 9) / 10)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
				if err := conn.WriteMessage(websocket.PingMessage, nil); err != nil {
					log.Printf("Ping error: %v", err)
					return
				}
			case <-done:
				return
			}
		}
	}()

	subMsg := `{
      "jsonrpc": "2.0",
      "method": "subscribe",
      "id": "0",
      "params": {
        "query": "tm.event='Tx'"
      }
    }`
	if err := conn.WriteMessage(websocket.TextMessage, []byte(subMsg)); err != nil {
		log.Fatal("write error:", err)
	}
	for {
		_, message, err := conn.ReadMessage()
		if err != nil {
			log.Println("read error:", err)
		}

		var tx_notification TxNotification
		json.Unmarshal(message, &tx_notification)
		//log.Printf("received: %s \n", tx_notification.Result.Data.Value.TxResult.Tx)
		for _, h := range tx_notification.Result.Events.TxHeight {
			iheight, _ := strconv.ParseInt(h, 10, 64)
			if last_height < iheight {
				last_height = iheight
			}
		}
		for {
			decoded, err := decode_tx(tx_notification.Result.Data.Value.TxResult.Tx)
			if err != nil {
				log.Printf("Failed to decode tx %s", err)
				continue
			} else {
				tx_hash_notification_chan <- *decoded
				break
			}
		}
	}
}

func listen_for_txs(tx_hash_notification_chan chan<- TxDecoded) {
	for {
		conn, _, err := websocket.DefaultDialer.Dial("ws://genesis-node:26657/websocket", nil)

		conn.SetPongHandler(func(string) error {
			return nil
		})

		if err != nil {
			log.Println("ws connection error:", err)
		}
		handle_connection(conn, tx_hash_notification_chan)
	}
}

func send_inference_req(private_key string) (InferenceId, error) {
	client, err := gonkaopenai.NewGonkaOpenAI(gonkaopenai.Options{
		GonkaPrivateKey: private_key,
	})
	if err != nil {
		return "", err
	}
	c, err := client.Chat.Completions.New(context.Background(), openai.ChatCompletionNewParams{
		Model: "Qwen/Qwen2.5-7B-Instruct",
		Messages: []openai.ChatCompletionMessageParamUnion{
			openai.UserMessage("Write a one-sentence bedtime story about a unicorn"),
		},
	})
	if err != nil {
		return "", err
	}
	return InferenceId(c.ID), nil
}

func generate_load(private_key string, rps int64, counter_chan chan int64, break_load_gen chan struct {}) {
  log.Printf("Generating load for %d RPS", rps)
	var request_interval = time.Second/time.Duration(rps)
	var i int64
	outer_start := time.Now()
  outerloop:
  for {
    i++
    counter_chan <- 1
		go func() {
			defer func() {
        counter_chan <- -1
      }()
			for {
				_, err := send_inference_req(private_key)
				if err != nil {
					continue
				}
				break
			}
		}()
    select {
    case <- break_load_gen:
      break outerloop
    default:
    }
		elapsed_time := time.Since(outer_start)
    wait_time := (request_interval * time.Duration(i)) - elapsed_time
    if wait_time > 0 {
      time.Sleep(wait_time)
    }
	}
	log.Printf("%d Threads created in %d milliseconds for %d RPS\n", i, time.Since(outer_start).Milliseconds(), rps)
}

//   - Gets the inference ids to watch for over a channel and adds them to watched_inferences
//   - Observes transactions from chain
//   - As soon as it observes both start/finish report the corresponding inference over
//     finished_inference_id_chan
func observe_and_report(tx_notification_chan chan TxDecoded, inference_id_watch_chan chan InferenceId, finished_inference_id_chan chan InferenceId, start_inference_recording_chan chan (chan struct {})) {
	record_inferences := false
	type ObservedTxKey struct {
		inferenceId InferenceId
		messageType string
	}
	watched_inferences := make(map[InferenceId]bool)
	observed_txs := make(map[ObservedTxKey]TxMessage)
	for {

		for watched_inference_id, _ := range watched_inferences {
			_, start_inf_exists := observed_txs[ObservedTxKey{inferenceId: watched_inference_id, messageType: "/inference.inference.MsgStartInference"}]
			_, finish_inf_exists := observed_txs[ObservedTxKey{inferenceId: watched_inference_id, messageType: "/inference.inference.MsgFinishInference"}]
			if finish_inf_exists && start_inf_exists {
				record_inferences = false
				finished_inference_id_chan <- watched_inference_id
				// clear watched item and empty cached transactions
				delete(watched_inferences, watched_inference_id)
				observed_txs = make(map[ObservedTxKey]TxMessage)
			}
		}

		select {
		case new_inference_tx := <-tx_notification_chan:
			if record_inferences {
				for _, msg := range new_inference_tx.Body.Messages {
					observed_txs[ObservedTxKey{inferenceId: msg.InferenceId, messageType: msg.MessageType}] = msg
				}
			}
		case new_watch := <-inference_id_watch_chan:
			watched_inferences[new_watch] = true

		case reply_chan := <-start_inference_recording_chan:
			record_inferences = true
			reply_chan <- struct {}{}
		}
	}
}

func generate_load_for_rps(private_key string, set_rps_chan chan int64, counter_chan chan int64, break_load_gen chan struct {}) {
	for {
		rps := <-set_rps_chan
		if rps > 0 {
			generate_load(private_key, rps, counter_chan, break_load_gen)
		}
	}
}

func main() {
  // Depends on GONKA_PRIVATE_KEY and GONKA_ENDPOINTS
	private_key := os.Getenv("GONKA_PRIVATE_KEY")
	if private_key == "" {
		log.Fatal("GONKA_PRIVATE_KEY is not set")
	}

	tx_notification_chan := make(chan TxDecoded, 10)
	start_inference_recording_chan := make(chan (chan struct {}), 10)
	inference_id_watch_chan := make(chan InferenceId, 10)
	finished_inference_id_chan := make(chan InferenceId, 10)

	go observe_and_report(tx_notification_chan, inference_id_watch_chan, finished_inference_id_chan, start_inference_recording_chan)

	go listen_for_txs(tx_notification_chan)

	set_rps_chan := make(chan int64, 10)
	counter_chan := make(chan int64, 10)
	break_load_gen := make(chan struct {}, 10)
  var counter int64 = 0
  go func() {
    for {
    i := <- counter_chan
    //log.Printf("%d", i)
    counter += i
  }}()
	go generate_load_for_rps(private_key, set_rps_chan, counter_chan, break_load_gen)

	var result []([]int64)

  rpsList := make([]int64, 12)
  for i := range rpsList {
      rpsList[i] = (int64(i) + 1) * 30
  }
	for _, rps := range rpsList {

		var timings []int64
    set_rps_chan <- rps
		for i := 1; i <= 3; i++ {

			start_recording_response_chan := make(chan struct {})
			start_inference_recording_chan <- start_recording_response_chan
			_ = <-start_recording_response_chan

			var inference_sent_at time.Time
			var probe_id InferenceId
			var err error
			for {
				inference_sent_at = time.Now()
				probe_id, err = send_inference_req(private_key)
				if err != nil {
					log.Printf("Failed to send probe req %d: %s retrying...", i, err)
				} else {
					log.Printf("Sent probe %d with %d pending requests: %s\n", i, counter, probe_id)
					break
				}
			}
			log.Printf("Waiting for probe: %s\n", probe_id)
			inference_id_watch_chan <- probe_id
			for {
				finished_id := <-finished_inference_id_chan
				if finished_id == probe_id {
					transaction_included_in := time.Since(inference_sent_at).Milliseconds()
					timings = append(timings, transaction_included_in)
					log.Printf("Finished %v probe in: %d millisecond\n", probe_id, transaction_included_in)
					break
				}
			}
		}
    break_load_gen <- struct {}{}
		result = append(result, []int64{rps, slices.Min(timings), slices.Max(timings)})
	}
	log.Printf("Result:\n%v\n", result)
}
