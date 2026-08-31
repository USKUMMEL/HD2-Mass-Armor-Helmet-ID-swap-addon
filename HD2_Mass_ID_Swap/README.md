# HD2_Mass_ID_Swap

Blender addon độc lập dùng cùng HD2SDK Community Edition.

## Workflow hiện có

1. Trong tab Modding của HD2SDK, thêm các `Unit` nguồn vào active patch (icon shield/tick của SDK).
2. Trong `View3D > Sidebar > ID_Swap > HD2_Mass_ID_Swap`, bấm **Add Unit Entries Already in Patch** để đưa các Unit đó vào danh sách **Source armor Units**.
3. Bấm dấu `+` tại **Destination archives**, tìm bằng friendly name hoặc ID, rồi thêm một hoặc nhiều armor đích. Ba nút **Light**, **Medium**, **Heavy** thêm nhanh toàn bộ archive đích trong nhóm đó.

Destination archive chỉ là nơi tool sẽ quét Unit/armor ID ở bước tạo patch sau này. User không phải tự nhập từng armor ID.

## Tạo patch

Sau khi đã có source và destination, bấm **Generate & Write ID-Swap Patch**. Tool tự chạy toàn bộ preflight trước khi ghi file:

- TOC order không được dùng để map. Tool dùng `Armor_List.json` với khóa **BodyType + slot + layer**: ví dụ `Slim/left_arm/undergarment` chỉ có thể thay đúng slot đó.
- Tool kiểm tra BodyType thật trong `CustomizationInfo` của cả source lẫn destination. JSON không có metadata cho một Unit đang tồn tại, BodyType sai, hoặc một global ID bị yêu cầu làm hai slot khác nhau đều sẽ chặn ghi patch.
- Mỗi source Unit được tra slot từ `Armor_List.json`. Source slot được dùng lại ở tất cả destination có cùng slot; payload của source chỉ lưu một lần trong patch.
- Source slot không tồn tại trong destination đang chọn không làm tool dừng; Analyze báo slot đó là `Skipped` và patch không ghi payload không có nơi sử dụng.
- Slot destination không có source sẽ không có override trong patch, nên vẫn dùng mesh gốc của armor đích.
- Bật **Use source from another body type** nếu muốn một source `Slim` thay cả target `Stocky` (hoặc ngược lại) có cùng `slot + layer`. Tool chỉ làm điều này khi có đúng một source khả dụng; nếu mơ hồ thì giữ mesh gốc.
- Trước khi copy nguyên Unit data, tool so `BonesRef`, `CompositeRef` và `StateMachineRef` của source/target. Rig khác nhau sẽ được giữ nguyên target thay vì ghi patch, tránh skinning mesh rung hoặc giật.
- Source Unit được sao chép nguyên ba blob `TocData`, `GpuData`, `StreamData`; không reserialize source khi chỉ ID swap.
- Payload được dedup bằng hash nội dung. Cùng source Unit chỉ được lưu một lần trong patch; mọi target Unit ID dùng source đó alias tới cùng offset dữ liệu.

Unit ID là global. Preflight báo số archive package ngoài destination cũng chứa các ID sắp patch. Mặc định tool chặn ghi; chỉ bật **Allow shared IDs** nếu chấp nhận các resource dùng chung này có thể tác động tới armor khác.

Tool tự tạo patch từ Base Archive nếu HD2SDK chưa có active patch. Trong cùng Blender scene, lần generate sau sẽ chỉ thay các Unit override do addon generate trước đó, không xoá entry khác của patch. Khi nâng từ bản cũ hoặc đang có patch cũ không rõ nguồn, hãy dùng một active patch sạch để tránh entry Unit cũ tiếp tục có hiệu lực.

Không bấm nút **Patch Archive** mặc định của HD2SDK sau khi tool ghi patch, vì writer mặc định của SDK sẽ ghi lặp payload cho từng ID.

## Cài đặt

Trong Blender, vào `Edit > Preferences > Add-ons > Install…`, chọn ZIP của addon rồi bật **HD2 Armor Multi Swap**. HD2SDK phải được cài và bật trước.

ZIP chính thức `HD2SDK-CommunityEditionV3-9-8.zip` cài module `HD2SDK-CommunityEdition`; addon nhận diện cả tên này và tên `HD2SDK` đã đổi. Giữ `armor_units_detailed.json` ở cùng cấp với thư mục addon khi cài ZIP.
