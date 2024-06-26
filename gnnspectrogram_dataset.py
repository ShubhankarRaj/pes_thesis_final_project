import torch
import csv
from PIL import Image
from torchvision import transforms
import numpy as np
from torch.utils.data import Dataset
from transformers import AutoTokenizer
from torch.nn.utils.rnn import pad_sequence
import pickle


class SpectrogramBaseDataset(Dataset):
    def __init__(self, dataset_name, hip, dataset_type, tokenizer: AutoTokenizer):
        super(SpectrogramBaseDataset, self).__init__()
        assert dataset_name in ['IEMOCAP', 'MELD', 'EmoryNLP', 'DailyDialog'], 'only support IEMOCAP, MELD, EmoryNLP'
        if dataset_name == 'IEMOCAP':
            assert dataset_type in ['train', 'test'], 'IEMOCAP only supports train and test'
        else:
            assert dataset_type in ['train', 'dev', 'test'], '(MELD/EmoryNLP/DailyDialog) only support train dev and test'
        self.dataset_name = dataset_name
        self.dataset_type = dataset_type
        self.hip = hip
        dataset_path = 'bert_data/' + dataset_name + '/' + dataset_name + '_graph_hip' + str(self.hip) + '_new.pkl'
        edge_attr_path = 'bert_data/' + dataset_name + '/' + dataset_name + '_edge_attr_' + dataset_type + '_1.pkl'
        # if dataset_name == 'IEMOCAP':
        #     data = pickle.load(open(dataset_path, 'rb'), encoding='utf-8')
        #     data = data[dataset_type]
        # else:
        data = pickle.load(open(dataset_path, 'rb'), encoding='utf-8')
        data = data[dataset_type]
        self.conversation = []
        self.utt = data[0]
        self.label = data[1]
        self.spk = data[2]
        graph = data[3]
        self.edge_index = graph['edge_index']
        self.edge_type = graph['edge_type']
        self.utt_id = []
        self.wmask = []
        for conv in self.utt:
            # print(conv)
            input_ids = []
            attention_mask = []
            for u in conv:
                encoded_inputs = tokenizer(u, truncation=True, max_length=52)
                input_ids.append(torch.tensor(encoded_inputs['input_ids'], dtype=torch.long))
                attention_mask.append(torch.tensor(encoded_inputs['attention_mask'], dtype=torch.float))
            self.conversation.append(conv)
            self.utt_id.append(input_ids)
            self.wmask.append(attention_mask)
        self.cmsk = pickle.load(open(edge_attr_path, 'rb'), encoding='utf-8')
        self.length = len(self.label)

    def __getitem__(self, item):
        selected_utt = self.utt_id[item]
        selected_label = self.label[item]
        selected_mask = self.wmask[item]
        selected_uttm = [1] * len(selected_label)
        if self.dataset_name == 'IEMOCAP':
            selected_spk = [0 if s == 'M' else 1 for s in self.spk[item]]
        else:
            selected_spk = self.spk[item]
        selected_edge_index = self.edge_index[item]
        selected_edge_type = self.edge_type[item]
        selected_cmsk = self.cmsk[item]
        selected_edge_attr = []
        selected_edge_relation_binary = []
        selected_edge_relation = []
        for i in range(selected_edge_index.shape[1]):
            edge_i = selected_edge_index[0, i]
            eg_tp = selected_edge_type[i]
            selected_edge_attr.append(torch.tensor(selected_cmsk[edge_i][eg_tp]))

            edge_j = selected_edge_index[1, i]
            selected_edge_relation_binary.append(1 if eg_tp == 'oWant' else 0)
            if edge_j <= edge_i:
                selected_edge_relation.append(2)
            else:
                if eg_tp == 'xWant':
                    selected_edge_relation.append(0)
                else:
                    selected_edge_relation.append(1)

        selected_utt = pad_sequence(selected_utt, batch_first=True, padding_value=0)
        selected_label = torch.tensor(selected_label, dtype=torch.long)
        selected_mask = pad_sequence(selected_mask, batch_first=True, padding_value=0)
        selected_uttm = torch.tensor(selected_uttm, dtype=torch.float)
        selected_spk = torch.tensor(selected_spk, dtype=torch.float)
        selected_edge_index = torch.tensor(selected_edge_index, dtype=torch.long)
        selected_edge_attr = torch.stack(selected_edge_attr, dim=0)
        selected_edge_relation_binary = torch.tensor(selected_edge_relation_binary, dtype=torch.long)
        selected_edge_relation = torch.tensor(selected_edge_relation, dtype=torch.long)
        # Setting the conversation item as it is
        selected_conversation = self.conversation[item]
        image_tensor_list = _get_spectrogram_image_tensors(selected_conversation, selected_label)
        return selected_utt, selected_mask, selected_label, selected_uttm, selected_spk, selected_edge_index, selected_edge_attr, selected_edge_relation_binary, selected_edge_relation, image_tensor_list

    def __len__(self):
        return self.length


def _get_spectrogram_image_tensors(conversation_list, label_tensor):
    zipped_conv_label = zip(conversation_list, label_tensor)
    spectrogram_image_path_list = []
    spectrogram_image_tensor_list = []
    transform = transforms.ToTensor()
    for each_conv, label in zipped_conv_label:
        spectrogram_image_path = _supplement_train_data_with_spectrograms(each_conv,label.item())
        spectrogram_image_path_list.append(spectrogram_image_path)
    #for spectrogram_image in spectrogram_image_path_list:
    #    print(spectrogram_image)
    #    image = Image.open(spectrogram_image)
    #    image_tensor = transform(image)
    #    spectrogram_image_tensor_list.append(image_tensor)
    return spectrogram_image_path_list


def collate_fn(data):
    data = data[0]
    utt, mask, label, uttm, spk, edge_index, edge_attr, edge_rel_b, edge_rel, image_tensor = data
    return utt, mask, label, uttm, spk, edge_index, edge_attr, edge_rel_b, edge_rel, image_tensor

def _supplement_train_data_with_spectrograms(uttm:str, label:int,):
    spectrogram_image_path_for_utterance = ""
    DATA_ROOT_PATH='/content/gdrive/MyDrive/emotion_detection_using_sound'
    IEMOCAP_ROOT_FLDR = f"{DATA_ROOT_PATH}/data/Processed_Data_Iemocap"
    IEMOCAP_PROCESSED_FLDR = f"{IEMOCAP_ROOT_FLDR}/iemocap_spectrograms"
    IEMOCAP_TRANSCRIPT_DOC = f"{IEMOCAP_ROOT_FLDR}/iemocapTrans.csv"
    IEMOCAP_EMOTION_FOLDER_MAPPING = {
        "exc":"excited",
        "ang":"angry",
        "fru":"frustrated",
        "hap":"happy",
        "neu":"neutral",
        "sad":"sad"
        }
    LABEL_EMOTION_MAPPING = {
        0:'hap',
        1:'sad',
        2:'neu',
        3:'ang',
        4:'exc',
        5:'fru'
        }
    # Generate the path of the SPECTROGRAM image
    with open(IEMOCAP_TRANSCRIPT_DOC, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        # Getting the emotion value for the label
        utt_emotion = LABEL_EMOTION_MAPPING[label]
        for index, row in enumerate(reader):
            if ((row['to_translate']).strip() == uttm) and ((row['emotion']).strip() == utt_emotion):
                # print(f"CSV VALUES: {row['to_translate']} | UTTM: {uttm} | LABEL: {label} , type: {type(label)}")
                spectrogram_image_folder = IEMOCAP_EMOTION_FOLDER_MAPPING[utt_emotion]
                spectrogram_image_path_for_utterance = f"{IEMOCAP_PROCESSED_FLDR}/{spectrogram_image_folder}/{row['title']}.wav.jpeg"
                break
    return spectrogram_image_path_for_utterance

def collate_fn_batch(data):
    utt, mask, label, uttm, spk, edge_index, edge_attr, edge_rel_b, edge_rel = [], [], [], [], [], [], [], [], []
    for d in data:
        utt.append(d[0])
        mask.append(d[1])
        label.append(d[2])
        uttm.append(d[3])
        spk.append(d[4])
        edge_index.append(d[5])
        edge_attr.append(d[6])
        edge_rel_b.append(d[7])
        edge_rel.append(d[8])
    return utt, mask, label, uttm, spk, edge_index, edge_attr, edge_rel_b, edge_rel
