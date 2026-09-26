import os


class DataConfig:
    data_name = ""
    root_dir = ""
    label_transform = "norm"

    def get_data_config(self, data_name):
        self.data_name = data_name
        if data_name == 'LEVIR':
            self.root_dir = os.getenv("LEVIR_PATH", "./samples")
        elif data_name == 'quick_start':
            self.root_dir = './samples/'
        elif data_name == 'SYSU':
            self.root_dir = os.getenv("SYSU_PATH", "./datasets/SYSU-CD")
        elif data_name == 'LuojiaSET-CLCD':
            self.root_dir = os.getenv(
                "LUOJIA_PATH",
                "./datasets/LuojiaSET-CLCD"
            )
        else:
            raise TypeError('%s has not defined' % data_name)
        return self


if __name__ == '__main__':
    # 👇 测试用，改成SYSU验证路径
    data = DataConfig().get_data_config(data_name='SYSU')
    print(data.data_name)
    print(data.root_dir)
    print(data.label_transform)